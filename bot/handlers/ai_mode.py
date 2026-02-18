"""AI mode handlers: /mode, branch selection and chat flow."""
import logging
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
    await message.answer(
        "Выберите режим работы:",
        reply_markup=mode_select_kb(user.current_mode),
    )


@router.callback_query(F.data == "ai_mode:menu")
async def cb_mode_menu(callback: CallbackQuery, session: AsyncSession, state: FSMContext) -> None:
    await state.clear()
    user = await _get_user(callback.from_user.id, session)
    if not user:
        await callback.answer("Сначала выполните /start", show_alert=True)
        return
    await callback.message.edit_text(
        "Выберите режим работы:",
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

    dialog_id = str(message.chat.id)
    session.add(
        AIDialogMessage(
            user_id=message.from_user.id,
            branch_id=branch.id,
            dialog_id=dialog_id,
            role="user",
            content=message.text,
            created_at=datetime.utcnow(),
        )
    )

    context_query = select(AIDialogMessage).where(
        AIDialogMessage.user_id == message.from_user.id,
        AIDialogMessage.branch_id == branch.id,
        AIDialogMessage.dialog_id == dialog_id,
    )
    if branch.context_retention_days is not None:
        context_query = context_query.where(
            AIDialogMessage.created_at >= datetime.utcnow() - timedelta(days=branch.context_retention_days)
        )
    context_query = context_query.order_by(desc(AIDialogMessage.created_at))
    if branch.max_messages_in_context is not None:
        context_query = context_query.limit(branch.max_messages_in_context)

    ctx_res = await session.execute(context_query)
    ctx_messages = list(reversed(list(ctx_res.scalars().all())))
    dialog_context = [{"role": m.role, "content": m.content} for m in ctx_messages]

    prompt_res = await session.execute(
        select(PromptTemplate).where(PromptTemplate.id == branch.system_prompt_id)
    )
    prompt_template = prompt_res.scalar_one_or_none()
    system_prompt = prompt_template.content if prompt_template else ""

    llm_client = LLMClient()
    answer = await llm_client.generate_reply(
        gpt_model=branch.gpt_model,
        system_prompt=system_prompt,
        dialog_context=dialog_context,
        user_message=message.text,
    )

    session.add(
        AIDialogMessage(
            user_id=message.from_user.id,
            branch_id=branch.id,
            dialog_id=dialog_id,
            role="assistant",
            content=answer,
            created_at=datetime.utcnow(),
        )
    )

    state_res = await session.execute(
        select(AIDialogState).where(
            AIDialogState.user_id == message.from_user.id,
            AIDialogState.branch_id == branch.id,
            AIDialogState.dialog_id == dialog_id,
        )
    )
    dialog_state = state_res.scalar_one_or_none()
    if dialog_state is None:
        dialog_state = AIDialogState(
            user_id=message.from_user.id,
            branch_id=branch.id,
            dialog_id=dialog_id,
            is_converted=False,
            has_negative=False,
            phone_number=None,
            last_client_message_at=datetime.utcnow(),
        )
        session.add(dialog_state)
    else:
        dialog_state.last_client_message_at = datetime.utcnow()

    await message.answer(answer)
