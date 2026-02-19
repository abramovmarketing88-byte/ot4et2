"""Profile-centric AI mode handlers."""
import json
import logging
import re
from datetime import datetime, timedelta

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.keyboards import mode_select_kb, profiles_for_ai_kb
from bot.states import AiSellerStates
from core.database.models import AIDialogMessage, AIDialogState, AISettings, FollowupStep, ScheduledFollowup, User
from core.llm.client import LLMClient

logger = logging.getLogger(__name__)
router = Router(name="ai_mode")

_PHONE_RE = re.compile(r"\+?7?\s*\(?\d{3}\)?\s*\d{3}[-\s]?\d{2}[-\s]?\d{2}")


def _detect_phone(text: str) -> str | None:
    m = _PHONE_RE.search(text)
    if not m:
        return None
    return re.sub(r"\D", "", m.group(0))[-10:] or None


def _detect_negative(text: str, ai: AISettings) -> bool:
    phrases = ["не интересно", "не надо", "не буду", "не хочу"]
    if ai.negative_phrases:
        try:
            phrases.extend(json.loads(ai.negative_phrases))
        except Exception:
            pass
    low = text.lower()
    return any(p.lower() in low for p in phrases)


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
    await message.answer("Выберите режим работы:", reply_markup=mode_select_kb(user.current_mode))




@router.callback_query(F.data == "ai_mode:menu")
async def cb_mode_menu(callback: CallbackQuery, session: AsyncSession, state: FSMContext) -> None:
    await state.clear()
    user = await _get_user(callback.from_user.id, session)
    if not user:
        await callback.answer("Сначала выполните /start", show_alert=True)
        return
    await callback.message.edit_text("Выберите режим работы:", reply_markup=mode_select_kb(user.current_mode))
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
        rows = await session.execute(select(AISettings.profile_id).where(AISettings.is_enabled == True))
        enabled_ids = {r[0] for r in rows.all()}
        from core.database.models import AvitoProfile
        own_rows = await session.execute(select(AvitoProfile.id).where(AvitoProfile.owner_id == callback.from_user.id))
        profile_ids = [r[0] for r in own_rows.all() if r[0] in enabled_ids]
        await state.set_state(AiSellerStates.choosing_branch)
        await callback.message.edit_text("ИИ режим включен. Выберите профиль:", reply_markup=profiles_for_ai_kb(profile_ids, user.current_branch_id))
    else:
        await callback.message.edit_text("Режим отчётности активирован.", reply_markup=mode_select_kb(user.current_mode))
    await callback.answer()


@router.callback_query(F.data.startswith("ai_profile:select:"))
async def cb_select_profile(callback: CallbackQuery, session: AsyncSession, state: FSMContext) -> None:
    profile_id = int(callback.data.split(":")[2])
    user = await _get_user(callback.from_user.id, session)
    if not user:
        await callback.answer("Сначала выполните /start", show_alert=True)
        return
    ai = await session.get(AISettings, profile_id)
    if not ai:
        await callback.answer("Настройки AI не найдены", show_alert=True)
        return
    user.current_branch_id = profile_id
    await state.set_state(AiSellerStates.chatting)
    await callback.message.edit_text(f"Выбран профиль #{profile_id}. Отправьте сообщение.")
    await callback.answer()


@router.message(AiSellerStates.chatting, F.text)
async def ai_chat_message(message: Message, session: AsyncSession) -> None:
    if not message.from_user:
        return
    text = (message.text or "").strip()
    if not text or text.startswith("/"):
        return

    user = await _get_user(message.from_user.id, session)
    if not user or user.current_mode != "ai_seller" or not user.current_branch_id:
        return

    profile_id = user.current_branch_id
    ai = await session.get(AISettings, profile_id)
    if not ai or not ai.is_enabled:
        await message.answer("AI отключён для профиля.")
        return

    now = datetime.utcnow()
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    daily_count = await session.scalar(select(func.count()).select_from(AIDialogMessage).where(AIDialogMessage.profile_id == profile_id, AIDialogMessage.role == "user", AIDialogMessage.created_at >= day_start))
    if daily_count and daily_count >= ai.daily_dialog_limit and ai.block_on_limit:
        return

    per_minute_count = await session.scalar(select(func.count()).select_from(AIDialogMessage).where(AIDialogMessage.profile_id == profile_id, AIDialogMessage.role == "user", AIDialogMessage.created_at >= now - timedelta(minutes=1)))
    if per_minute_count and per_minute_count >= ai.messages_per_minute_limit:
        await message.answer("Слишком много сообщений. Подождите немного.")
        return

    dialog_id = "default"
    session.add(AIDialogMessage(user_id=message.from_user.id, profile_id=profile_id, dialog_id=dialog_id, role="user", content=text, created_at=now))

    state_row = await session.get(AIDialogState, {"user_id": message.from_user.id, "profile_id": profile_id, "dialog_id": dialog_id})
    just_started = False
    if state_row is None:
        state_row = AIDialogState(user_id=message.from_user.id, profile_id=profile_id, dialog_id=dialog_id)
        session.add(state_row)
        just_started = True

    state_row.last_client_message_at = now
    phone = _detect_phone(text)
    if phone:
        state_row.is_converted = True
        state_row.phone_number = phone
    if _detect_negative(text, ai):
        state_row.has_negative = True

    await session.commit()

    context_q = select(AIDialogMessage).where(AIDialogMessage.user_id == message.from_user.id, AIDialogMessage.profile_id == profile_id, AIDialogMessage.dialog_id == dialog_id)
    if ai.context_retention_days:
        context_q = context_q.where(AIDialogMessage.created_at >= now - timedelta(days=ai.context_retention_days))
    context_q = context_q.order_by(desc(AIDialogMessage.created_at))
    if ai.max_messages_in_context:
        context_q = context_q.limit(ai.max_messages_in_context)
    ctx = list(reversed((await session.execute(context_q)).scalars().all()))
    messages = [{"role": "system", "content": ai.system_prompt or ""}] + [{"role": m.role, "content": m.content} for m in ctx]

    llm = LLMClient()
    answer = await llm.generate_reply(ai, messages)

    session.add(AIDialogMessage(user_id=message.from_user.id, profile_id=profile_id, dialog_id=dialog_id, role="assistant", content=answer, created_at=datetime.utcnow()))
    await session.commit()

    if just_started:
        steps = (await session.execute(select(FollowupStep).where(FollowupStep.profile_id == profile_id, FollowupStep.is_active == True).order_by(FollowupStep.order_index.asc()))).scalars().all()
        for step in steps:
            session.add(ScheduledFollowup(user_id=message.from_user.id, profile_id=profile_id, step_id=step.id, dialog_id=dialog_id, execute_at=datetime.utcnow() + timedelta(seconds=step.delay_seconds), status="pending", converted=state_row.is_converted, negative_detected=state_row.has_negative))
        await session.commit()

    if ai.summary_mode != "off" and (state_row.is_converted or (ai.stop_on_negative and state_row.has_negative)) and ai.summary_target_chat_id:
        await message.bot.send_message(ai.summary_target_chat_id, f"Сводка: профиль={profile_id} конвертирован={state_row.is_converted} негатив={state_row.has_negative}")

    await message.answer(answer)
