"""Profile-centric AI mode handlers."""
import json
import logging
import re
from datetime import datetime, timedelta

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.keyboards import (
    ai_profile_hub_kb,
    ai_set_context_kb,
    ai_set_delay_kb,
    ai_set_format_kb,
    ai_set_handoff_kb,
    ai_set_limits_kb,
    ai_set_model_kb,
    ai_set_notify_chat_kb,
    ai_set_prompt_kb,
    ai_set_stopwords_kb,
    mode_select_kb,
    profiles_for_ai_kb,
)
from bot.states import AiSettingsStates, AiSellerStates
from core.database.models import (
    AIDialogMessage,
    AIDialogState,
    AISettings,
    AvitoProfile,
    FollowupStep,
    PromptTemplate,
    ScheduledFollowup,
    User,
)
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
        # Same resolution as /profiles: profiles by owner_id == telegram_id (no ai_settings filter)
        profiles_result = await session.execute(
            select(AvitoProfile).where(AvitoProfile.owner_id == callback.from_user.id)
        )
        profiles = list(profiles_result.scalars().all())
        await state.set_state(AiSellerStates.choosing_branch)
        await callback.message.edit_text(
            "Выберите профиль для настройки ИИ:",
            reply_markup=profiles_for_ai_kb(profiles, user.current_branch_id),
        )
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
    profile_row = await session.execute(
        select(AvitoProfile).where(
            AvitoProfile.id == profile_id,
            AvitoProfile.owner_id == callback.from_user.id,
        )
    )
    profile = profile_row.scalar_one_or_none()
    if not profile:
        await callback.answer("Профиль не найден.", show_alert=True)
        return
    ai = await session.get(AISettings, profile_id)
    if ai is None:
        ai = AISettings(profile_id=profile_id, is_enabled=False, model_alias="gpt-4o-mini")
        session.add(ai)
        await session.flush()
    user.current_branch_id = profile_id
    await state.clear()
    await callback.message.edit_text(
        f"🤖 ИИ-продавец — профиль: <b>{profile.profile_name}</b>",
        reply_markup=ai_profile_hub_kb(profile_id, profile.profile_name, ai.is_enabled),
    )
    await callback.answer()


@router.callback_query(F.data == "ai_profile:back_to_list")
async def cb_ai_profile_back_to_list(callback: CallbackQuery, session: AsyncSession, state: FSMContext) -> None:
    await state.clear()
    user = await _get_user(callback.from_user.id, session)
    if not user:
        await callback.answer("Сначала выполните /start", show_alert=True)
        return
    profiles_result = await session.execute(
        select(AvitoProfile).where(AvitoProfile.owner_id == callback.from_user.id)
    )
    profiles = list(profiles_result.scalars().all())
    await callback.message.edit_text(
        "Выберите профиль для настройки ИИ:",
        reply_markup=profiles_for_ai_kb(profiles, user.current_branch_id),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("ai_profile:test_chat:"))
async def cb_ai_profile_test_chat(callback: CallbackQuery, session: AsyncSession, state: FSMContext) -> None:
    profile_id = int(callback.data.split(":")[2])
    user = await _get_user(callback.from_user.id, session)
    if not user:
        await callback.answer("Сначала выполните /start", show_alert=True)
        return
    profile_row = await session.execute(
        select(AvitoProfile).where(
            AvitoProfile.id == profile_id,
            AvitoProfile.owner_id == callback.from_user.id,
        )
    )
    profile = profile_row.scalar_one_or_none()
    if not profile:
        await callback.answer("Профиль не найден.", show_alert=True)
        return
    ai = await session.get(AISettings, profile_id)
    if ai is None:
        ai = AISettings(profile_id=profile_id, is_enabled=False, model_alias="gpt-4o-mini")
        session.add(ai)
        await session.flush()
    user.current_branch_id = profile_id
    user.current_mode = "ai_seller"
    await state.set_state(AiSellerStates.chatting)
    await callback.message.edit_text(
        f"💬 Тест-чат — <b>{profile.profile_name}</b>. Отправьте сообщение."
    )
    await callback.answer()


async def _get_profile_ai(
    telegram_id: int, profile_id: int, session: AsyncSession
) -> tuple[AvitoProfile, AISettings] | None:
    r = await session.execute(
        select(AvitoProfile).where(
            AvitoProfile.id == profile_id,
            AvitoProfile.owner_id == telegram_id,
        )
    )
    profile = r.scalar_one_or_none()
    if not profile:
        return None
    ai = await session.get(AISettings, profile_id)
    if ai is None:
        ai = AISettings(profile_id=profile_id, is_enabled=False, model_alias="gpt-4o-mini")
        session.add(ai)
        await session.flush()
    return (profile, ai)


async def _show_hub(
    callback: CallbackQuery,
    profile: AvitoProfile,
    ai: AISettings,
) -> None:
    await callback.message.edit_text(
        f"🤖 ИИ-продавец — профиль: <b>{profile.profile_name}</b>",
        reply_markup=ai_profile_hub_kb(profile.id, profile.profile_name, ai.is_enabled),
    )


@router.callback_query(F.data.startswith("ai_set:back_hub:"))
async def cb_ai_set_back_hub(callback: CallbackQuery, session: AsyncSession, state: FSMContext) -> None:
    await state.clear()
    try:
        profile_id = int(callback.data.split(":")[2])
    except (IndexError, ValueError):
        await callback.answer("Ошибка.", show_alert=True)
        return
    pair = await _get_profile_ai(callback.from_user.id, profile_id, session)
    if not pair:
        await callback.answer("Профиль не найден.", show_alert=True)
        return
    profile, ai = pair
    await _show_hub(callback, profile, ai)
    await callback.answer()


@router.callback_query(F.data.startswith("ai_set:toggle:"))
async def cb_ai_set_toggle(callback: CallbackQuery, session: AsyncSession, state: FSMContext) -> None:
    try:
        profile_id = int(callback.data.split(":")[2])
    except (IndexError, ValueError):
        await callback.answer("Ошибка.", show_alert=True)
        return
    pair = await _get_profile_ai(callback.from_user.id, profile_id, session)
    if not pair:
        await callback.answer("Профиль не найден.", show_alert=True)
        return
    profile, ai = pair
    ai.is_enabled = not ai.is_enabled
    if not ai.is_enabled:
        r = await session.execute(
            select(ScheduledFollowup).where(
                ScheduledFollowup.profile_id == profile_id,
                ScheduledFollowup.status == "pending",
            )
        )
        for item in r.scalars().all():
            item.status = "canceled"
    await _show_hub(callback, profile, ai)
    await callback.answer()


@router.callback_query(F.data.startswith("ai_set:prompt:"))
async def cb_ai_set_prompt(callback: CallbackQuery, session: AsyncSession) -> None:
    try:
        profile_id = int(callback.data.split(":")[2])
    except (IndexError, ValueError):
        await callback.answer("Ошибка.", show_alert=True)
        return
    pair = await _get_profile_ai(callback.from_user.id, profile_id, session)
    if not pair:
        await callback.answer("Профиль не найден.", show_alert=True)
        return
    _, ai = pair
    preview = (ai.system_prompt or "").strip()[:300]
    if len((ai.system_prompt or "").strip()) > 300:
        preview += "..."
    text = f"🧠 <b>Основной промпт</b>\n\n{preview or '(пусто)'}"
    await callback.message.edit_text(text, reply_markup=ai_set_prompt_kb(profile_id))
    await callback.answer()


@router.callback_query(F.data.startswith("ai_set:prompt_full:"))
async def cb_ai_set_prompt_full(callback: CallbackQuery, session: AsyncSession) -> None:
    """Отправить полный текст промпта отдельным сообщением (части при длине > 4000)."""
    try:
        profile_id = int(callback.data.split(":")[2])
    except (IndexError, ValueError):
        await callback.answer("Ошибка.", show_alert=True)
        return
    pair = await _get_profile_ai(callback.from_user.id, profile_id, session)
    if not pair:
        await callback.answer("Профиль не найден.", show_alert=True)
        return
    _, ai = pair
    full_text = (ai.system_prompt or "").strip()
    if not full_text:
        await callback.answer("Промпт пуст.", show_alert=True)
        return
    chunk_size = 4000
    for i in range(0, len(full_text), chunk_size):
        chunk = full_text[i : i + chunk_size]
        prefix = "🧠 <b>Основной промпт (полностью)</b>:\n\n" if i == 0 else ""
        await callback.message.answer(prefix + chunk)
    await callback.answer("Отправлено.")


@router.callback_query(F.data.startswith("ai_set:prompt_edit:"))
async def cb_ai_set_prompt_edit(callback: CallbackQuery, session: AsyncSession, state: FSMContext) -> None:
    try:
        profile_id = int(callback.data.split(":")[2])
    except (IndexError, ValueError):
        await callback.answer("Ошибка.", show_alert=True)
        return
    pair = await _get_profile_ai(callback.from_user.id, profile_id, session)
    if not pair:
        await callback.answer("Профиль не найден.", show_alert=True)
        return
    await state.update_data(ai_set_profile_id=profile_id)
    await state.set_state(AiSettingsStates.waiting_prompt_text)
    await callback.message.edit_text(
        "Введите новый текст системного промпта (одним сообщением):",
        reply_markup=InlineKeyboardBuilder().row(
            InlineKeyboardButton(text="⬅ Отмена", callback_data=f"ai_set:back_hub:{profile_id}")
        ).as_markup(),
    )
    await callback.answer()


@router.message(AiSettingsStates.waiting_prompt_text, F.text)
async def ai_set_prompt_text(message: Message, session: AsyncSession, state: FSMContext) -> None:
    data = await state.get_data()
    profile_id = data.get("ai_set_profile_id")
    if not profile_id:
        await state.clear()
        return
    pair = await _get_profile_ai(message.from_user.id, profile_id, session)
    if not pair:
        await state.clear()
        await message.answer("Профиль не найден.")
        return
    _, ai = pair
    ai.system_prompt = (message.text or "").strip()
    await state.clear()
    preview = (ai.system_prompt or "").strip()[:300]
    if len((ai.system_prompt or "").strip()) > 300:
        preview += "..."
    await message.answer(
        f"✅ Промпт сохранён.\n\n🧠 <b>Основной промпт</b>\n\n{preview or '(пусто)'}",
        reply_markup=ai_set_prompt_kb(profile_id),
    )


@router.callback_query(F.data.startswith("ai_set:prompt_tpl:"))
async def cb_ai_set_prompt_tpl(callback: CallbackQuery, session: AsyncSession) -> None:
    try:
        profile_id = int(callback.data.split(":")[2])
    except (IndexError, ValueError):
        await callback.answer("Ошибка.", show_alert=True)
        return
    pair = await _get_profile_ai(callback.from_user.id, profile_id, session)
    if not pair:
        await callback.answer("Профиль не найден.", show_alert=True)
        return
    profile, ai = pair
    r = await session.execute(
        select(PromptTemplate).where(PromptTemplate.owner_id == callback.from_user.id)
    )
    templates = list(r.scalars().all())
    if not templates:
        await callback.answer("Нет шаблонов. Создайте через /prompts.", show_alert=True)
        return
    b = InlineKeyboardBuilder()
    for t in templates:
        b.row(InlineKeyboardButton(text=t.name, callback_data=f"ai_set:prompt_tpl_sel:{profile_id}:{t.id}"))
    b.row(InlineKeyboardButton(text="⬅ Назад", callback_data=f"ai_set:back_hub:{profile_id}"))
    await callback.message.edit_text("📚 Выберите шаблон:", reply_markup=b.as_markup())
    await callback.answer()


@router.callback_query(F.data.startswith("ai_set:prompt_tpl_sel:"))
async def cb_ai_set_prompt_tpl_sel(callback: CallbackQuery, session: AsyncSession) -> None:
    parts = callback.data.split(":")
    if len(parts) < 4:
        await callback.answer("Ошибка.", show_alert=True)
        return
    profile_id, tpl_id = int(parts[2]), int(parts[3])
    pair = await _get_profile_ai(callback.from_user.id, profile_id, session)
    if not pair:
        await callback.answer("Профиль не найден.", show_alert=True)
        return
    _, ai = pair
    tpl = await session.get(PromptTemplate, tpl_id)
    if tpl and tpl.owner_id == callback.from_user.id:
        ai.system_prompt = tpl.content or ""
        preview = (ai.system_prompt or "")[:300] + ("..." if len(ai.system_prompt or "") > 300 else "")
        await callback.message.edit_text(f"🧠 <b>Основной промпт</b>\n\n{preview}", reply_markup=ai_set_prompt_kb(profile_id))
    await callback.answer("✅ Шаблон применён.")


@router.callback_query(F.data.startswith("ai_set:prompt_file:"))
async def cb_ai_set_prompt_file(callback: CallbackQuery, session: AsyncSession, state: FSMContext) -> None:
    try:
        profile_id = int(callback.data.split(":")[2])
    except (IndexError, ValueError):
        await callback.answer("Ошибка.", show_alert=True)
        return
    pair = await _get_profile_ai(callback.from_user.id, profile_id, session)
    if not pair:
        await callback.answer("Профиль не найден.", show_alert=True)
        return
    await state.update_data(ai_set_profile_id=profile_id)
    await state.set_state(AiSettingsStates.waiting_prompt_text)
    await callback.message.edit_text(
        "Отправьте .txt файл с текстом промпта:",
        reply_markup=InlineKeyboardBuilder().row(
            InlineKeyboardButton(text="⬅ Отмена", callback_data=f"ai_set:back_hub:{profile_id}")
        ).as_markup(),
    )
    await callback.answer()


@router.message(AiSettingsStates.waiting_prompt_text, F.document)
async def ai_set_prompt_file_upload(message: Message, session: AsyncSession, state: FSMContext) -> None:
    if not message.document or not message.bot:
        return
    fn = (message.document.file_name or "").lower()
    if not fn.endswith(".txt"):
        await message.answer("Нужен файл .txt")
        return
    data = await state.get_data()
    profile_id = data.get("ai_set_profile_id")
    if not profile_id:
        await state.clear()
        return
    pair = await _get_profile_ai(message.from_user.id, profile_id, session)
    if not pair:
        await state.clear()
        await message.answer("Профиль не найден.")
        return
    _, ai = pair
    f = await message.bot.get_file(message.document.file_id)
    content = await message.bot.download_file(f.file_path)
    text = content.read().decode("utf-8", errors="ignore")
    ai.system_prompt = text.strip()
    await state.clear()
    await message.answer("✅ Промпт загружен из файла.", reply_markup=ai_set_prompt_kb(profile_id))


@router.callback_query(F.data.startswith("ai_set:context:"))
async def cb_ai_set_context(callback: CallbackQuery, session: AsyncSession) -> None:
    try:
        profile_id = int(callback.data.split(":")[2])
    except (IndexError, ValueError):
        await callback.answer("Ошибка.", show_alert=True)
        return
    pair = await _get_profile_ai(callback.from_user.id, profile_id, session)
    if not pair:
        await callback.answer("Профиль не найден.", show_alert=True)
        return
    _, ai = pair
    mode = getattr(ai, "context_mode", "last_n") or "last_n"
    val = getattr(ai, "context_value", 20) or 20
    if mode == "all":
        disp = "Весь контекст"
    elif mode == "last_n":
        disp = f"Последние {val} сообщений"
    else:
        disp = f"За последние {val} ч"
    await callback.message.edit_text(
        f"📚 <b>Контекст диалога</b>\n\nТекущий режим: {disp}",
        reply_markup=ai_set_context_kb(profile_id),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("ai_set:ctx_all:"))
async def cb_ai_set_ctx_all(callback: CallbackQuery, session: AsyncSession) -> None:
    try:
        profile_id = int(callback.data.split(":")[2])
    except (IndexError, ValueError):
        await callback.answer("Ошибка.", show_alert=True)
        return
    pair = await _get_profile_ai(callback.from_user.id, profile_id, session)
    if not pair:
        await callback.answer("Профиль не найден.", show_alert=True)
        return
    _, ai = pair
    ai.context_mode = "all"
    await callback.message.edit_text(
        "📚 <b>Контекст диалога</b>\n\nТекущий режим: Весь контекст",
        reply_markup=ai_set_context_kb(profile_id),
    )
    await callback.answer("✅ Установлено: весь контекст.")


@router.callback_query(F.data.startswith("ai_set:ctx_lastn:"))
async def cb_ai_set_ctx_lastn(callback: CallbackQuery, session: AsyncSession, state: FSMContext) -> None:
    try:
        profile_id = int(callback.data.split(":")[2])
    except (IndexError, ValueError):
        await callback.answer("Ошибка.", show_alert=True)
        return
    pair = await _get_profile_ai(callback.from_user.id, profile_id, session)
    if not pair:
        await callback.answer("Профиль не найден.", show_alert=True)
        return
    await state.update_data(ai_set_profile_id=profile_id, ai_set_ctx_type="last_n")
    await state.set_state(AiSettingsStates.waiting_context_value)
    await callback.message.edit_text(
        "Введите число N (последние N сообщений):",
        reply_markup=InlineKeyboardBuilder().row(
            InlineKeyboardButton(text="⬅ Отмена", callback_data=f"ai_set:back_hub:{profile_id}")
        ).as_markup(),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("ai_set:ctx_hours:"))
async def cb_ai_set_ctx_hours(callback: CallbackQuery, session: AsyncSession, state: FSMContext) -> None:
    try:
        profile_id = int(callback.data.split(":")[2])
    except (IndexError, ValueError):
        await callback.answer("Ошибка.", show_alert=True)
        return
    pair = await _get_profile_ai(callback.from_user.id, profile_id, session)
    if not pair:
        await callback.answer("Профиль не найден.", show_alert=True)
        return
    await state.update_data(ai_set_profile_id=profile_id, ai_set_ctx_type="time_window")
    await state.set_state(AiSettingsStates.waiting_context_value)
    await callback.message.edit_text(
        "Введите число N (часов):",
        reply_markup=InlineKeyboardBuilder().row(
            InlineKeyboardButton(text="⬅ Отмена", callback_data=f"ai_set:back_hub:{profile_id}")
        ).as_markup(),
    )
    await callback.answer()


@router.message(AiSettingsStates.waiting_context_value, F.text)
async def ai_set_context_value(message: Message, session: AsyncSession, state: FSMContext) -> None:
    data = await state.get_data()
    profile_id = data.get("ai_set_profile_id")
    ctx_type = data.get("ai_set_ctx_type", "last_n")
    if not profile_id:
        await state.clear()
        return
    if not message.text or not message.text.strip().isdigit():
        await message.answer("Введите целое число.")
        return
    n = int(message.text.strip())
    if n <= 0:
        await message.answer("Число должно быть больше 0.")
        return
    pair = await _get_profile_ai(message.from_user.id, profile_id, session)
    if not pair:
        await state.clear()
        await message.answer("Профиль не найден.")
        return
    _, ai = pair
    ai.context_mode = ctx_type
    ai.context_value = n
    await state.clear()
    disp = f"Последние {n} сообщений" if ctx_type == "last_n" else f"За последние {n} ч"
    await message.answer(f"✅ Контекст: {disp}.", reply_markup=ai_set_context_kb(profile_id))


@router.callback_query(F.data.startswith("ai_set:format:"))
async def cb_ai_set_format(callback: CallbackQuery, session: AsyncSession) -> None:
    try:
        profile_id = int(callback.data.split(":")[2])
    except (IndexError, ValueError):
        await callback.answer("Ошибка.", show_alert=True)
        return
    pair = await _get_profile_ai(callback.from_user.id, profile_id, session)
    if not pair:
        await callback.answer("Профиль не найден.", show_alert=True)
        return
    _, ai = pair
    mode = getattr(ai, "message_mode", "single") or "single"
    cnt = getattr(ai, "message_sentences_count", None)
    disp = "Одним сообщением" if mode == "single" else f"По {cnt or '?'} предложений"
    await callback.message.edit_text(
        f"✍ <b>Формат сообщений</b>\n\nТекущий режим: {disp}",
        reply_markup=ai_set_format_kb(profile_id),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("ai_set:fmt_single:"))
async def cb_ai_set_fmt_single(callback: CallbackQuery, session: AsyncSession) -> None:
    try:
        profile_id = int(callback.data.split(":")[2])
    except (IndexError, ValueError):
        await callback.answer("Ошибка.", show_alert=True)
        return
    pair = await _get_profile_ai(callback.from_user.id, profile_id, session)
    if not pair:
        await callback.answer("Профиль не найден.", show_alert=True)
        return
    _, ai = pair
    ai.message_mode = "single"
    ai.message_sentences_count = None
    await callback.message.edit_text(
        "✍ <b>Формат сообщений</b>\n\nТекущий режим: Одним сообщением",
        reply_markup=ai_set_format_kb(profile_id),
    )
    await callback.answer("✅ Одним сообщением.")


@router.callback_query(F.data.startswith("ai_set:fmt_sentences:"))
async def cb_ai_set_fmt_sentences(callback: CallbackQuery, session: AsyncSession, state: FSMContext) -> None:
    try:
        profile_id = int(callback.data.split(":")[2])
    except (IndexError, ValueError):
        await callback.answer("Ошибка.", show_alert=True)
        return
    pair = await _get_profile_ai(callback.from_user.id, profile_id, session)
    if not pair:
        await callback.answer("Профиль не найден.", show_alert=True)
        return
    await state.update_data(ai_set_profile_id=profile_id)
    await state.set_state(AiSettingsStates.waiting_message_sentences)
    await callback.message.edit_text(
        "Введите N (разбивать по N предложений):",
        reply_markup=InlineKeyboardBuilder().row(
            InlineKeyboardButton(text="⬅ Отмена", callback_data=f"ai_set:back_hub:{profile_id}")
        ).as_markup(),
    )
    await callback.answer()


@router.message(AiSettingsStates.waiting_message_sentences, F.text)
async def ai_set_message_sentences(message: Message, session: AsyncSession, state: FSMContext) -> None:
    data = await state.get_data()
    profile_id = data.get("ai_set_profile_id")
    if not profile_id:
        await state.clear()
        return
    if not message.text or not message.text.strip().isdigit():
        await message.answer("Введите целое число.")
        return
    n = int(message.text.strip())
    if n <= 0:
        await message.answer("Число должно быть больше 0.")
        return
    pair = await _get_profile_ai(message.from_user.id, profile_id, session)
    if not pair:
        await state.clear()
        await message.answer("Профиль не найден.")
        return
    _, ai = pair
    ai.message_mode = "by_sentences"
    ai.message_sentences_count = n
    await state.clear()
    await message.answer(f"✅ Разбивать по {n} предложений.", reply_markup=ai_set_format_kb(profile_id))


@router.callback_query(F.data.startswith("ai_set:delay:"))
async def cb_ai_set_delay(callback: CallbackQuery, session: AsyncSession) -> None:
    try:
        profile_id = int(callback.data.split(":")[2])
    except (IndexError, ValueError):
        await callback.answer("Ошибка.", show_alert=True)
        return
    pair = await _get_profile_ai(callback.from_user.id, profile_id, session)
    if not pair:
        await callback.answer("Профиль не найден.", show_alert=True)
        return
    _, ai = pair
    sec = getattr(ai, "response_delay_seconds", 10) or 10
    await callback.message.edit_text(
        f"⏳ <b>Задержка ответа</b>\n\nТекущее значение: {sec} сек.",
        reply_markup=ai_set_delay_kb(profile_id),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("ai_set:delay_edit:"))
async def cb_ai_set_delay_edit(callback: CallbackQuery, session: AsyncSession, state: FSMContext) -> None:
    try:
        profile_id = int(callback.data.split(":")[2])
    except (IndexError, ValueError):
        await callback.answer("Ошибка.", show_alert=True)
        return
    pair = await _get_profile_ai(callback.from_user.id, profile_id, session)
    if not pair:
        await callback.answer("Профиль не найден.", show_alert=True)
        return
    await state.update_data(ai_set_profile_id=profile_id)
    await state.set_state(AiSettingsStates.waiting_delay_seconds)
    await callback.message.edit_text(
        "Введите задержку в секундах (целое число):",
        reply_markup=InlineKeyboardBuilder().row(
            InlineKeyboardButton(text="⬅ Отмена", callback_data=f"ai_set:back_hub:{profile_id}")
        ).as_markup(),
    )
    await callback.answer()


@router.message(AiSettingsStates.waiting_delay_seconds, F.text)
async def ai_set_delay_seconds(message: Message, session: AsyncSession, state: FSMContext) -> None:
    data = await state.get_data()
    profile_id = data.get("ai_set_profile_id")
    if not profile_id:
        await state.clear()
        return
    if not message.text or not message.text.strip().isdigit():
        await message.answer("Введите целое число секунд.")
        return
    sec = int(message.text.strip())
    if sec < 0:
        await message.answer("Число не должно быть отрицательным.")
        return
    pair = await _get_profile_ai(message.from_user.id, profile_id, session)
    if not pair:
        await state.clear()
        await message.answer("Профиль не найден.")
        return
    _, ai = pair
    ai.response_delay_seconds = sec
    await state.clear()
    await message.answer(f"✅ Задержка: {sec} сек.", reply_markup=ai_set_delay_kb(profile_id))


@router.callback_query(F.data.startswith("ai_set:limits:"))
async def cb_ai_set_limits(callback: CallbackQuery, session: AsyncSession) -> None:
    try:
        profile_id = int(callback.data.split(":")[2])
    except (IndexError, ValueError):
        await callback.answer("Ошибка.", show_alert=True)
        return
    pair = await _get_profile_ai(callback.from_user.id, profile_id, session)
    if not pair:
        await callback.answer("Профиль не найден.", show_alert=True)
        return
    _, ai = pair
    txt = (
        f"🚦 <b>Ограничения</b>\n\n"
        f"📨 Макс сообщений в диалоге: {ai.per_dialog_message_limit}\n"
        f"📅 Макс диалогов в день: {ai.daily_dialog_limit}\n"
        f"⏳ Мин пауза между ответами: {getattr(ai, 'min_pause_seconds', 0)} сек."
    )
    await callback.message.edit_text(txt, reply_markup=ai_set_limits_kb(profile_id))
    await callback.answer()


@router.callback_query(F.data.startswith("ai_set:limit_dialog:"))
async def cb_ai_set_limit_dialog(callback: CallbackQuery, session: AsyncSession, state: FSMContext) -> None:
    try:
        profile_id = int(callback.data.split(":")[2])
    except (IndexError, ValueError):
        await callback.answer("Ошибка.", show_alert=True)
        return
    pair = await _get_profile_ai(callback.from_user.id, profile_id, session)
    if not pair:
        await callback.answer("Профиль не найден.", show_alert=True)
        return
    await state.update_data(ai_set_profile_id=profile_id, ai_set_limit_key="dialog")
    await state.set_state(AiSettingsStates.waiting_limit_value)
    await callback.message.edit_text(
        "Введите макс. число сообщений в диалоге:",
        reply_markup=InlineKeyboardBuilder().row(
            InlineKeyboardButton(text="⬅ Отмена", callback_data=f"ai_set:back_hub:{profile_id}")
        ).as_markup(),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("ai_set:limit_daily:"))
async def cb_ai_set_limit_daily(callback: CallbackQuery, session: AsyncSession, state: FSMContext) -> None:
    try:
        profile_id = int(callback.data.split(":")[2])
    except (IndexError, ValueError):
        await callback.answer("Ошибка.", show_alert=True)
        return
    pair = await _get_profile_ai(callback.from_user.id, profile_id, session)
    if not pair:
        await callback.answer("Профиль не найден.", show_alert=True)
        return
    await state.update_data(ai_set_profile_id=profile_id, ai_set_limit_key="daily")
    await state.set_state(AiSettingsStates.waiting_limit_value)
    await callback.message.edit_text(
        "Введите макс. диалогов в день:",
        reply_markup=InlineKeyboardBuilder().row(
            InlineKeyboardButton(text="⬅ Отмена", callback_data=f"ai_set:back_hub:{profile_id}")
        ).as_markup(),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("ai_set:limit_pause:"))
async def cb_ai_set_limit_pause(callback: CallbackQuery, session: AsyncSession, state: FSMContext) -> None:
    try:
        profile_id = int(callback.data.split(":")[2])
    except (IndexError, ValueError):
        await callback.answer("Ошибка.", show_alert=True)
        return
    pair = await _get_profile_ai(callback.from_user.id, profile_id, session)
    if not pair:
        await callback.answer("Профиль не найден.", show_alert=True)
        return
    await state.update_data(ai_set_profile_id=profile_id, ai_set_limit_key="pause")
    await state.set_state(AiSettingsStates.waiting_limit_value)
    await callback.message.edit_text(
        "Введите мин. паузу между ответами (секунды):",
        reply_markup=InlineKeyboardBuilder().row(
            InlineKeyboardButton(text="⬅ Отмена", callback_data=f"ai_set:back_hub:{profile_id}")
        ).as_markup(),
    )
    await callback.answer()


@router.message(AiSettingsStates.waiting_limit_value, F.text)
async def ai_set_limit_value(message: Message, session: AsyncSession, state: FSMContext) -> None:
    data = await state.get_data()
    profile_id = data.get("ai_set_profile_id")
    key = data.get("ai_set_limit_key")
    if not profile_id or not key:
        await state.clear()
        return
    if not message.text or not message.text.strip().isdigit():
        await message.answer("Введите целое число.")
        return
    n = int(message.text.strip())
    if n < 0:
        await message.answer("Число не должно быть отрицательным.")
        return
    pair = await _get_profile_ai(message.from_user.id, profile_id, session)
    if not pair:
        await state.clear()
        await message.answer("Профиль не найден.")
        return
    _, ai = pair
    if key == "dialog":
        ai.per_dialog_message_limit = n
    elif key == "daily":
        ai.daily_dialog_limit = n
    else:
        ai.min_pause_seconds = n
    await state.clear()
    txt = (
        f"🚦 <b>Ограничения</b>\n\n"
        f"📨 Макс сообщений в диалоге: {ai.per_dialog_message_limit}\n"
        f"📅 Макс диалогов в день: {ai.daily_dialog_limit}\n"
        f"⏳ Мин пауза между ответами: {getattr(ai, 'min_pause_seconds', 0)} сек."
    )
    await message.answer(txt, reply_markup=ai_set_limits_kb(profile_id))


@router.callback_query(F.data.startswith("ai_set:stopwords:"))
async def cb_ai_set_stopwords(callback: CallbackQuery, session: AsyncSession) -> None:
    try:
        profile_id = int(callback.data.split(":")[2])
    except (IndexError, ValueError):
        await callback.answer("Ошибка.", show_alert=True)
        return
    pair = await _get_profile_ai(callback.from_user.id, profile_id, session)
    if not pair:
        await callback.answer("Профиль не найден.", show_alert=True)
        return
    _, ai = pair
    words = (ai.stop_words or "").strip() or "(не заданы)"
    await callback.message.edit_text(
        f"🛑 <b>Стоп-слова</b>\n\nПри наличии слова в сообщении клиента ИИ перестаёт отвечать.\n\nТекущий список: {words}",
        reply_markup=ai_set_stopwords_kb(profile_id),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("ai_set:stopwords_edit:"))
async def cb_ai_set_stopwords_edit(callback: CallbackQuery, session: AsyncSession, state: FSMContext) -> None:
    try:
        profile_id = int(callback.data.split(":")[2])
    except (IndexError, ValueError):
        await callback.answer("Ошибка.", show_alert=True)
        return
    pair = await _get_profile_ai(callback.from_user.id, profile_id, session)
    if not pair:
        await callback.answer("Профиль не найден.", show_alert=True)
        return
    await state.update_data(ai_set_profile_id=profile_id)
    await state.set_state(AiSettingsStates.waiting_stop_words)
    await callback.message.edit_text(
        "Введите стоп-слова через запятую:",
        reply_markup=InlineKeyboardBuilder().row(
            InlineKeyboardButton(text="⬅ Отмена", callback_data=f"ai_set:back_hub:{profile_id}")
        ).as_markup(),
    )
    await callback.answer()


@router.message(AiSettingsStates.waiting_stop_words, F.text)
async def ai_set_stop_words_msg(message: Message, session: AsyncSession, state: FSMContext) -> None:
    data = await state.get_data()
    profile_id = data.get("ai_set_profile_id")
    if not profile_id:
        await state.clear()
        return
    pair = await _get_profile_ai(message.from_user.id, profile_id, session)
    if not pair:
        await state.clear()
        await message.answer("Профиль не найден.")
        return
    _, ai = pair
    ai.stop_words = (message.text or "").strip() or None
    await state.clear()
    await message.answer("✅ Стоп-слова сохранены.", reply_markup=ai_set_stopwords_kb(profile_id))


@router.callback_query(F.data.startswith("ai_set:notify_chat:"))
async def cb_ai_set_notify_chat(callback: CallbackQuery, session: AsyncSession) -> None:
    try:
        profile_id = int(callback.data.split(":")[2])
    except (IndexError, ValueError):
        await callback.answer("Ошибка.", show_alert=True)
        return
    pair = await _get_profile_ai(callback.from_user.id, profile_id, session)
    if not pair:
        await callback.answer("Профиль не найден.", show_alert=True)
        return
    _, ai = pair
    chat_id = ai.summary_target_chat_id or "(не задан)"
    await callback.message.edit_text(
        f"👥 <b>Чат уведомлений</b>\n\nСюда отправляются: получен номер, ИИ остановлен, передача сотруднику, саммари.\n\nТекущий chat_id: {chat_id}",
        reply_markup=ai_set_notify_chat_kb(profile_id),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("ai_set:notify_forward:"))
async def cb_ai_set_notify_forward(callback: CallbackQuery, session: AsyncSession, state: FSMContext) -> None:
    try:
        profile_id = int(callback.data.split(":")[2])
    except (IndexError, ValueError):
        await callback.answer("Ошибка.", show_alert=True)
        return
    pair = await _get_profile_ai(callback.from_user.id, profile_id, session)
    if not pair:
        await callback.answer("Профиль не найден.", show_alert=True)
        return
    await state.update_data(ai_set_profile_id=profile_id)
    await state.set_state(AiSettingsStates.waiting_forward_for_chat)
    await callback.message.edit_text(
        "Перешлите сюда любое сообщение из чата/группы, куда слать уведомления:",
        reply_markup=InlineKeyboardBuilder().row(
            InlineKeyboardButton(text="⬅ Отмена", callback_data=f"ai_set:back_hub:{profile_id}")
        ).as_markup(),
    )
    await callback.answer()


@router.message(AiSettingsStates.waiting_forward_for_chat, F.forward_from_chat)
async def ai_set_notify_forward_done(message: Message, session: AsyncSession, state: FSMContext) -> None:
    data = await state.get_data()
    profile_id = data.get("ai_set_profile_id")
    if not profile_id:
        await state.clear()
        return
    chat_id = message.forward_from_chat.id if message.forward_from_chat else None
    if not chat_id:
        await message.answer("Не удалось определить чат. Перешлите сообщение из группы/канала.")
        return
    pair = await _get_profile_ai(message.from_user.id, profile_id, session)
    if not pair:
        await state.clear()
        await message.answer("Профиль не найден.")
        return
    _, ai = pair
    ai.summary_target_chat_id = chat_id
    await state.clear()
    await message.answer(f"✅ Чат уведомлений: {chat_id}.", reply_markup=ai_set_notify_chat_kb(profile_id))


@router.callback_query(F.data.startswith("ai_set:handoff:"))
async def cb_ai_set_handoff(callback: CallbackQuery, session: AsyncSession) -> None:
    try:
        profile_id = int(callback.data.split(":")[2])
    except (IndexError, ValueError):
        await callback.answer("Ошибка.", show_alert=True)
        return
    pair = await _get_profile_ai(callback.from_user.id, profile_id, session)
    if not pair:
        await callback.answer("Профиль не найден.", show_alert=True)
        return
    _, ai = pair
    stop = getattr(ai, "stop_on_employee_message", True)
    ret = getattr(ai, "auto_return_enabled", False)
    mins = getattr(ai, "auto_return_minutes", None) or "—"
    txt = (
        f"🔄 <b>Передача управления</b>\n\n"
        f"Останавливать ИИ при сообщении сотрудника: {'Да' if stop else 'Нет'}\n"
        f"Авто-возврат ИИ: {'Да' if ret else 'Нет'}\n"
        f"Время возврата (мин): {mins}"
    )
    await callback.message.edit_text(txt, reply_markup=ai_set_handoff_kb(profile_id))
    await callback.answer()


@router.callback_query(F.data.startswith("ai_set:handoff_toggle_stop:"))
async def cb_ai_set_handoff_toggle_stop(callback: CallbackQuery, session: AsyncSession) -> None:
    try:
        profile_id = int(callback.data.split(":")[2])
    except (IndexError, ValueError):
        await callback.answer("Ошибка.", show_alert=True)
        return
    pair = await _get_profile_ai(callback.from_user.id, profile_id, session)
    if not pair:
        await callback.answer("Профиль не найден.", show_alert=True)
        return
    _, ai = pair
    ai.stop_on_employee_message = not ai.stop_on_employee_message
    await callback.answer(f"✅ {'Вкл' if ai.stop_on_employee_message else 'Выкл'} остановку при сообщении сотрудника.")
    await cb_ai_set_handoff(callback, session)


@router.callback_query(F.data.startswith("ai_set:handoff_toggle_return:"))
async def cb_ai_set_handoff_toggle_return(callback: CallbackQuery, session: AsyncSession) -> None:
    try:
        profile_id = int(callback.data.split(":")[2])
    except (IndexError, ValueError):
        await callback.answer("Ошибка.", show_alert=True)
        return
    pair = await _get_profile_ai(callback.from_user.id, profile_id, session)
    if not pair:
        await callback.answer("Профиль не найден.", show_alert=True)
        return
    _, ai = pair
    ai.auto_return_enabled = not ai.auto_return_enabled
    await callback.answer(f"✅ Авто-возврат: {'вкл' if ai.auto_return_enabled else 'выкл'}.")
    await cb_ai_set_handoff(callback, session)


@router.callback_query(F.data.startswith("ai_set:handoff_minutes:"))
async def cb_ai_set_handoff_minutes(callback: CallbackQuery, session: AsyncSession, state: FSMContext) -> None:
    try:
        profile_id = int(callback.data.split(":")[2])
    except (IndexError, ValueError):
        await callback.answer("Ошибка.", show_alert=True)
        return
    pair = await _get_profile_ai(callback.from_user.id, profile_id, session)
    if not pair:
        await callback.answer("Профиль не найден.", show_alert=True)
        return
    await state.update_data(ai_set_profile_id=profile_id)
    await state.set_state(AiSettingsStates.waiting_auto_return_minutes)
    await callback.message.edit_text(
        "Введите время возврата управления ИИ (минуты):",
        reply_markup=InlineKeyboardBuilder().row(
            InlineKeyboardButton(text="⬅ Отмена", callback_data=f"ai_set:back_hub:{profile_id}")
        ).as_markup(),
    )
    await callback.answer()


@router.message(AiSettingsStates.waiting_auto_return_minutes, F.text)
async def ai_set_auto_return_minutes(message: Message, session: AsyncSession, state: FSMContext) -> None:
    data = await state.get_data()
    profile_id = data.get("ai_set_profile_id")
    if not profile_id:
        await state.clear()
        return
    if not message.text or not message.text.strip().isdigit():
        await message.answer("Введите целое число минут.")
        return
    n = int(message.text.strip())
    if n <= 0:
        await message.answer("Число должно быть больше 0.")
        return
    pair = await _get_profile_ai(message.from_user.id, profile_id, session)
    if not pair:
        await state.clear()
        await message.answer("Профиль не найден.")
        return
    _, ai = pair
    ai.auto_return_minutes = n
    await state.clear()
    await message.answer(f"✅ Время возврата: {n} мин.", reply_markup=ai_set_handoff_kb(profile_id))


@router.callback_query(F.data.startswith("ai_set:model:"))
async def cb_ai_set_model(callback: CallbackQuery, session: AsyncSession) -> None:
    try:
        profile_id = int(callback.data.split(":")[2])
    except (IndexError, ValueError):
        await callback.answer("Ошибка.", show_alert=True)
        return
    pair = await _get_profile_ai(callback.from_user.id, profile_id, session)
    if not pair:
        await callback.answer("Профиль не найден.", show_alert=True)
        return
    await callback.message.edit_text(
        "🤖 <b>Модель</b>\n\nДоступна только gpt-4o-mini.",
        reply_markup=ai_set_model_kb(profile_id),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("ai_set:model_confirm:"))
async def cb_ai_set_model_confirm(callback: CallbackQuery, session: AsyncSession) -> None:
    try:
        profile_id = int(callback.data.split(":")[2])
    except (IndexError, ValueError):
        await callback.answer("Ошибка.", show_alert=True)
        return
    pair = await _get_profile_ai(callback.from_user.id, profile_id, session)
    if not pair:
        await callback.answer("Профиль не найден.", show_alert=True)
        return
    _, ai = pair
    ai.model_alias = "gpt-4o-mini"
    await callback.answer("✅ gpt-4o-mini.")
    await cb_ai_set_model(callback, session)


@router.callback_query(F.data.startswith("ai_set:followups:"))
async def cb_ai_set_followups(callback: CallbackQuery, session: AsyncSession) -> None:
    try:
        profile_id = int(callback.data.split(":")[2])
    except (IndexError, ValueError):
        await callback.answer("Ошибка.", show_alert=True)
        return
    pair = await _get_profile_ai(callback.from_user.id, profile_id, session)
    if not pair:
        await callback.answer("Профиль не найден.", show_alert=True)
        return
    await callback.message.edit_text(
        "📩 <b>Фоллоу-апы</b>\n\nНастройка шагов: задержка, тип (текст/LLM), условие (не ответил / не отправил номер / всегда).",
        reply_markup=InlineKeyboardBuilder().row(
            InlineKeyboardButton(text="⬅ Назад", callback_data=f"ai_set:back_hub:{profile_id}")
        ).as_markup(),
    )
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
