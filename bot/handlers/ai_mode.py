"""AI mode handlers: /mode, branch selection and chat flow."""
import logging
import re
from datetime import datetime, timedelta

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.keyboards import ai_branches_kb, mode_select_kb
from bot.states import AiSellerStates
from core.database.models import AIBranch, AIDialogMessage, AIDialogState, PromptTemplate, User
from core.llm.client import LLMClient

logger = logging.getLogger(__name__)
router = Router(name="ai_mode")

# Russian phone: +7/8, optional spaces/dashes/parens, 10 digits
_PHONE_RE = re.compile(r"\+?7?\s*\(?\d{3}\)?\s*\d{3}[-\s]?\d{2}[-\s]?\d{2}")
# Negative intent phrases (lowercase)
_NEGATIVE_PHRASES = (
    "не интересно", "не надо", "отстань", "отвали", "хватит", "плохо", "ужас",
    "кошмар", "не буду", "не хочу", "не нужен", "не нужна", "не нужно",
)


def _detect_phone(text: str) -> str | None:
    m = _PHONE_RE.search(text)
    if not m:
        return None
    return re.sub(r"\D", "", m.group(0))[-10:] or None


def _detect_negative(text: str) -> bool:
    lower = text.lower()
    return any(p in lower for p in _NEGATIVE_PHRASES)


async def _get_user(telegram_id: int, session: AsyncSession) -> User | None:
    result = await session.execute(select(User).where(User.telegram_id == telegram_id))
    return result.scalar_one_or_none()


@router.message(Command("mode"))
async def cmd_mode(message: Message, session: AsyncSession, state: FSMContext) -> None:
    await state.clear()
    user = await _get_user(message.from_user.id, session)
    if not user:
        await message.answer("Сначала выполните /start")
        return
    mode_label = "ИИ-продавец" if user.current_mode == "ai_seller" else "Отчётность"
    await message.answer(
        f"Текущий режим: <b>{mode_label}</b>\n\nВыберите режим работы:",
        reply_markup=mode_select_kb(user.current_mode),
    )


@router.callback_query(F.data == "ai_mode:menu")
async def cb_mode_menu(callback: CallbackQuery, session: AsyncSession, state: FSMContext) -> None:
    await state.clear()
    user = await _get_user(callback.from_user.id, session)
    if not user:
        await callback.answer("Сначала выполните /start", show_alert=True)
        return
    mode_label = "ИИ-продавец" if user.current_mode == "ai_seller" else "Отчётность"
    await callback.message.edit_text(
        f"Текущий режим: <b>{mode_label}</b>\n\nВыберите режим работы:",
        reply_markup=mode_select_kb(user.current_mode),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("ai_mode:set:"))
async def cb_mode_set(callback: CallbackQuery, session: AsyncSession, state: FSMContext) -> None:
    mode = callback.data.split(":")[2]
    user = await _get_user(callback.from_user.id, session)
    if not user:
        await callback.answer("Сначала выполните /start", show_alert=True)
        return
    user.current_mode = mode
    await state.clear()
    if mode == "ai_seller":
        result = await session.execute(
            select(AIBranch.id, AIBranch.name).where(AIBranch.owner_id == callback.from_user.id)
        )
        branches = list(result.all())
        await state.set_state(AiSellerStates.choosing_branch)
        await callback.message.edit_text(
            "Режим ИИ-продавец активирован. Выберите ветку:",
            reply_markup=ai_branches_kb(branches, user.current_branch_id),
        )
    else:
        await callback.message.edit_text(
            "Режим отчётности активирован.",
            reply_markup=mode_select_kb(user.current_mode),
        )
    await callback.answer()


@router.callback_query(F.data.startswith("ai_branch:select:"))
async def cb_select_branch(callback: CallbackQuery, session: AsyncSession, state: FSMContext) -> None:
    branch_id = int(callback.data.split(":")[2])
    user = await _get_user(callback.from_user.id, session)
    if not user:
        await callback.answer("Сначала выполните /start", show_alert=True)
        return
    result = await session.execute(
        select(AIBranch).where(AIBranch.id == branch_id, AIBranch.owner_id == callback.from_user.id)
    )
    branch = result.scalar_one_or_none()
    if not branch:
        await callback.answer("Ветка не найдена", show_alert=True)
        return
    user.current_branch_id = branch.id
    await state.set_state(AiSellerStates.chatting)
    await callback.message.edit_text(f"Выбрана ветка: <b>{branch.name}</b>\nОтправьте сообщение.")
    await callback.answer()


@router.message(AiSellerStates.chatting, F.text)
async def ai_chat_message(message: Message, session: AsyncSession) -> None:
    if not message.from_user:
        return
    text = (message.text or "").strip()
    if text.startswith("/"):
        return
    user = await _get_user(message.from_user.id, session)
    if not user or user.current_mode != "ai_seller" or not user.current_branch_id:
        return

    result = await session.execute(
        select(AIBranch).where(
            AIBranch.id == user.current_branch_id,
            AIBranch.owner_id == message.from_user.id,
        )
    )
    branch = result.scalar_one_or_none()
    if not branch:
        await message.answer("Ветка не найдена. Выберите ветку через /mode")
        return

    user_id = message.from_user.id
    dialog_id = "default"

    # 1) Store user message
    session.add(
        AIDialogMessage(
            user_id=user_id,
            branch_id=branch.id,
            dialog_id=dialog_id,
            role="user",
            content=text,
            created_at=datetime.utcnow(),
        )
    )

    # 2) Get or create dialog_state, update last_client_message_at, phone, negative
    state_res = await session.execute(
        select(AIDialogState).where(
            AIDialogState.user_id == user_id,
            AIDialogState.branch_id == branch.id,
            AIDialogState.dialog_id == dialog_id,
        )
    )
    dialog_state = state_res.scalar_one_or_none()
    if dialog_state is None:
        dialog_state = AIDialogState(
            user_id=user_id,
            branch_id=branch.id,
            dialog_id=dialog_id,
            is_converted=False,
            has_negative=False,
            phone_number=None,
            last_client_message_at=None,
        )
        session.add(dialog_state)

    now = datetime.utcnow()
    dialog_state.last_client_message_at = now
    phone = _detect_phone(text)
    if phone:
        dialog_state.is_converted = True
        dialog_state.phone_number = phone
    if _detect_negative(text):
        dialog_state.has_negative = True

    # 3) Build context (retention_days, max_messages)
    context_query = select(AIDialogMessage).where(
        AIDialogMessage.user_id == user_id,
        AIDialogMessage.branch_id == branch.id,
        AIDialogMessage.dialog_id == dialog_id,
    )
    if branch.context_retention_days is not None:
        context_query = context_query.where(
            AIDialogMessage.created_at >= now - timedelta(days=branch.context_retention_days)
        )
    context_query = context_query.order_by(desc(AIDialogMessage.created_at))
    if branch.max_messages_in_context is not None:
        context_query = context_query.limit(branch.max_messages_in_context)
    ctx_res = await session.execute(context_query)
    ctx_messages = list(reversed(ctx_res.scalars().all()))
    dialog_context = [{"role": m.role, "content": m.content} for m in ctx_messages]

    # 4) System prompt
    prompt_res = await session.execute(
        select(PromptTemplate).where(PromptTemplate.id == branch.system_prompt_id)
    )
    prompt_template = prompt_res.scalar_one_or_none()
    system_prompt = prompt_template.content if prompt_template else ""

    # 5) LLM
    llm_client = LLMClient()
    messages: list[dict[str, Any]] = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.extend(dialog_context)
    answer = await llm_client.generate_reply(branch=branch, messages=messages)

    # 6) Store assistant reply
    session.add(
        AIDialogMessage(
            user_id=user_id,
            branch_id=branch.id,
            dialog_id=dialog_id,
            role="assistant",
            content=answer,
            created_at=datetime.utcnow(),
        )
    )

    await message.answer(answer)
