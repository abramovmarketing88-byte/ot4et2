"""Telegram интеграция: бот (целевой чат + тест), Telegram Business (инструкции + сохранение)."""
import json
import logging
from datetime import datetime

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, Update
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.keyboards import (
    integrations_menu_kb,
    telegram_bot_target_kb,
    telegram_business_status_kb,
    telegram_integration_kb,
)
from bot.states import TelegramIntegrationStates
from core.database.models import TelegramBusinessConnection, TelegramTarget, User
from core.services.telegram_targets import (
    get_active_target,
    get_or_create_target,
    get_target_by_id,
)

logger = logging.getLogger(__name__)
router = Router(name="telegram_integration")


def _parse_target_id(callback_data: str) -> int | None:
    """Безопасный разбор target_id из callback_data (tg_target:action:id)."""
    try:
        parts = callback_data.split(":")
        if len(parts) >= 3 and parts[0] == "tg_target":
            return int(parts[2])
    except (ValueError, IndexError):
        pass
    return None


async def _ensure_user(telegram_id: int, session: AsyncSession) -> bool:
    """Проверить, что пользователь есть в БД (для консистентности FK)."""
    r = await session.execute(select(User).where(User.telegram_id == telegram_id))
    return r.scalar_one_or_none() is not None


# ─── Навигация ─────────────────────────────────────────────────────────────

@router.callback_query(F.data == "intg:telegram")
async def cb_intg_telegram(
    callback: CallbackQuery, session: AsyncSession, state: FSMContext
) -> None:
    """Экран Telegram: бот, business, тест, назад."""
    await state.clear()
    await callback.message.edit_text(
        "✈️ <b>Telegram</b>\n\n"
        "• Подключите бота — укажите чат для уведомлений и тестовых сообщений.\n"
        "• Telegram Business — подключите личный аккаунт как бизнес.",
        reply_markup=telegram_integration_kb(),
    )
    await callback.answer()


# ─── Режим бота: целевой чат ─────────────────────────────────────────────────

@router.callback_query(F.data.startswith("tg_int:bot"))
async def cb_tg_int_bot(
    callback: CallbackQuery, session: AsyncSession, state: FSMContext
) -> None:
    """Экран настройки целевого чата (bot mode)."""
    await state.clear()
    telegram_id = callback.from_user.id if callback.from_user else 0
    if not await _ensure_user(telegram_id, session):
        await callback.answer("Сначала выполните /start.", show_alert=True)
        return
    target = await get_or_create_target(telegram_id, session)
    chat_status = str(target.target_chat_id) if target.target_chat_id else "не задан"
    welcome = (target.welcome_message or "").strip() or "не задано"
    text = (
        "🤖 <b>Подключить Telegram-бота</b>\n\n"
        f"Чат для уведомлений: <code>{chat_status}</code>\n"
        f"Тестовое сообщение: {welcome[:50] + '…' if len(welcome) > 50 else welcome or '—'}"
    )
    await callback.message.edit_text(
        text,
        reply_markup=telegram_bot_target_kb(target.id),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("tg_target:input_chat:"))
async def cb_tg_target_input_chat(
    callback: CallbackQuery, session: AsyncSession, state: FSMContext
) -> None:
    """Запрос ввода chat_id (вручную)."""
    raw_id = _parse_target_id(callback.data)
    telegram_id = callback.from_user.id if callback.from_user else 0
    if raw_id is not None and raw_id != 0:
        target = await get_target_by_id(raw_id, telegram_id, session)
        if not target:
            await callback.answer("Цель не найдена или доступ запрещён.", show_alert=True)
            return
        await state.update_data(tg_target_id=target.id)
    else:
        await state.update_data(tg_target_id=0)
    await state.set_state(TelegramIntegrationStates.waiting_chat_id)
    await callback.message.edit_text(
        "Введите <code>chat_id</code> чата (число). Или перешлите сообщение из чата.",
        reply_markup=__back_to_bot_kb(telegram_id),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("tg_target:forward:"))
async def cb_tg_target_forward(
    callback: CallbackQuery, session: AsyncSession, state: FSMContext
) -> None:
    """Ожидание пересланного сообщения из чата."""
    raw_id = _parse_target_id(callback.data)
    telegram_id = callback.from_user.id if callback.from_user else 0
    if raw_id is not None and raw_id != 0:
        target = await get_target_by_id(raw_id, telegram_id, session)
        if not target:
            await callback.answer("Цель не найдена или доступ запрещён.", show_alert=True)
            return
        await state.update_data(tg_target_id=target.id)
    else:
        await state.update_data(tg_target_id=0)
    await state.set_state(TelegramIntegrationStates.waiting_forward)
    await callback.message.edit_text(
        "Перешлите сюда любое сообщение из чата/группы, куда нужно отправлять уведомления.",
        reply_markup=__back_to_bot_kb(telegram_id),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("tg_target:welcome_msg:"))
async def cb_tg_target_welcome_msg(
    callback: CallbackQuery, session: AsyncSession, state: FSMContext
) -> None:
    """Ввод тестового/приветственного сообщения."""
    raw_id = _parse_target_id(callback.data)
    if raw_id is None or raw_id == 0:
        await callback.answer("Сначала укажите чат.", show_alert=True)
        return
    telegram_id = callback.from_user.id if callback.from_user else 0
    target = await get_target_by_id(raw_id, telegram_id, session)
    if not target:
        await callback.answer("Цель не найдена или доступ запрещён.", show_alert=True)
        return
    await state.update_data(tg_target_id=target.id)
    await state.set_state(TelegramIntegrationStates.waiting_welcome_message)
    await callback.message.edit_text(
        "Введите текст тестового/приветственного сообщения (одним сообщением):",
        reply_markup=__back_to_bot_kb(telegram_id),
    )
    await callback.answer()


def __back_to_bot_kb(telegram_id: int):
    from aiogram.types import InlineKeyboardButton
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    return InlineKeyboardBuilder().row(
        InlineKeyboardButton(text="⬅ Отмена", callback_data="intg:telegram")
    ).as_markup()


@router.message(TelegramIntegrationStates.waiting_chat_id, F.text)
async def msg_tg_chat_id(
    message: Message, session: AsyncSession, state: FSMContext
) -> None:
    """Сохранение введённого chat_id."""
    data = await state.get_data()
    target_id = data.get("tg_target_id", 0)
    telegram_id = message.from_user.id if message.from_user else 0
    raw = (message.text or "").strip().lstrip("-")
    if not raw.isdigit():
        await message.answer("Введите число (chat_id).")
        return
    chat_id = int(raw)
    if target_id == 0:
        target = await get_or_create_target(telegram_id, session)
    else:
        target = await get_target_by_id(target_id, telegram_id, session)
        if not target:
            await state.clear()
            await message.answer("Цель не найдена.")
            return
    target.target_chat_id = chat_id
    await state.clear()
    await message.answer(
        f"✅ Чат сохранён: <code>{chat_id}</code>.",
        reply_markup=telegram_bot_target_kb(target.id),
    )


@router.message(TelegramIntegrationStates.waiting_forward, F.forward_from_chat)
async def msg_tg_forward_from_chat(
    message: Message, session: AsyncSession, state: FSMContext
) -> None:
    """Сохранение chat_id из пересланного сообщения."""
    data = await state.get_data()
    target_id = data.get("tg_target_id", 0)
    telegram_id = message.from_user.id if message.from_user else 0
    chat_id = getattr(message.forward_from_chat, "id", None) if message.forward_from_chat else None
    if not chat_id:
        await message.answer("Не удалось определить чат. Перешлите сообщение из группы/канала.")
        return
    if target_id == 0:
        target = await get_or_create_target(telegram_id, session)
    else:
        target = await get_target_by_id(target_id, telegram_id, session)
        if not target:
            await state.clear()
            await message.answer("Цель не найдена.")
            return
    target.target_chat_id = int(chat_id)
    target.title = getattr(message.forward_from_chat, "title", None) or None
    await state.clear()
    await message.answer(
        f"✅ Чат сохранён: <code>{chat_id}</code>.",
        reply_markup=telegram_bot_target_kb(target.id),
    )


@router.message(TelegramIntegrationStates.waiting_welcome_message, F.text)
async def msg_tg_welcome(
    message: Message, session: AsyncSession, state: FSMContext
) -> None:
    """Сохранение тестового сообщения."""
    data = await state.get_data()
    target_id = data.get("tg_target_id")
    telegram_id = message.from_user.id if message.from_user else 0
    if not target_id:
        await state.clear()
        return
    target = await get_target_by_id(target_id, telegram_id, session)
    if not target:
        await state.clear()
        await message.answer("Цель не найдена.")
        return
    target.welcome_message = (message.text or "").strip() or None
    await state.clear()
    await message.answer("✅ Тестовое сообщение сохранено.", reply_markup=telegram_bot_target_kb(target.id))


# ─── Тест отправки ──────────────────────────────────────────────────────────

@router.callback_query(F.data == "tg_int:test_send")
async def cb_tg_int_test_send(
    callback: CallbackQuery, session: AsyncSession
) -> None:
    """Отправить тестовое сообщение в активный целевой чат."""
    telegram_id = callback.from_user.id if callback.from_user else 0
    target = await get_active_target(telegram_id, session)
    if not target:
        await callback.answer(
            "Сначала укажите чат в разделе «Подключить Telegram-бота».",
            show_alert=True,
        )
        return
    text = (target.welcome_message or "").strip() or "Тестовое сообщение от бота."
    try:
        await callback.bot.send_message(
            chat_id=target.target_chat_id,
            text=text,
        )
        await callback.answer("✅ Сообщение отправлено.")
    except Exception as e:
        logger.warning("Test send failed: %s", e)
        err = str(e).lower()
        if "chat not found" in err or "blocked" in err or "bot was blocked" in err:
            msg = "Чат не найден или бот заблокирован в этом чате."
        elif "not enough rights" in err or "forbidden" in err:
            msg = "Недостаточно прав: добавьте бота в чат и дайте право отправки сообщений."
        else:
            msg = "Ошибка отправки. Проверьте, что бот добавлен в чат и имеет право писать."
        await callback.answer(msg, show_alert=True)


# ─── Telegram Business: инструкции и статус ──────────────────────────────────

BUSINESS_INSTRUCTIONS = """
👤 <b>Подключение личного аккаунта (Telegram Business)</b>

1. Откройте <b>Настройки</b> → <b>Telegram Business</b> в приложении Telegram.
2. Нажмите <b>Подключить бота</b> и выберите этого бота из списка.
3. Подтвердите разрешения (ответы от имени аккаунта в чатах и т.д.).
4. После подключения бот сохранит данные соединения автоматически.

Статус подключения отображается ниже.
"""


@router.callback_query(F.data == "tg_int:business")
async def cb_tg_int_business(
    callback: CallbackQuery, session: AsyncSession, state: FSMContext
) -> None:
    """Экран Telegram Business: инструкции + статус."""
    await state.clear()
    telegram_id = callback.from_user.id if callback.from_user else 0
    r = await session.execute(
        select(TelegramBusinessConnection)
        .where(TelegramBusinessConnection.user_id == telegram_id)
        .order_by(TelegramBusinessConnection.updated_at.desc())
    )
    connections = list(r.scalars().all())
    status_lines = []
    if not connections:
        status_lines.append("Подключений пока нет. Выполните шаги выше.")
    else:
        for c in connections:
            active = "активно" if not c.is_disabled else "отключено"
            status_lines.append(
                f"• <code>{c.connection_id}</code> — {active}, обновлено {c.updated_at.strftime('%Y-%m-%d %H:%M')}"
            )
    text = BUSINESS_INSTRUCTIONS + "\n<b>Статус:</b>\n" + "\n".join(status_lines)
    await callback.message.edit_text(
        text,
        reply_markup=telegram_business_status_kb(),
    )
    await callback.answer()


# ─── Сохранение business_connection при апдейте ───────────────────────────────

def _has_business_connection(update: Update) -> bool:
    return getattr(update, "business_connection", None) is not None


@router.update(_has_business_connection)
async def on_business_connection_update(
    update: Update, session: AsyncSession
) -> None:
    """При подключении/отключении/изменении Business — сохранить в БД."""
    bc = getattr(update, "business_connection", None)
    if not bc:
        return
    try:
        connection_id = bc.id
        business_user_id = bc.user.id if bc.user else 0
        user_chat_id = getattr(bc, "user_chat_id", None)
        is_enabled = getattr(bc, "is_enabled", True)
        rights = getattr(bc, "rights", None)
        scope_json = None
        if rights is not None:
            scope_json = json.dumps({
                "can_reply": getattr(rights, "can_reply", None),
                "can_delete_messages": getattr(rights, "can_delete_messages", None),
            }, default=str)
        r = await session.execute(
            select(TelegramBusinessConnection).where(
                TelegramBusinessConnection.connection_id == connection_id
            )
        )
        row = r.scalar_one_or_none()
        if row:
            row.business_user_id = business_user_id
            row.user_chat_id = user_chat_id
            row.is_disabled = not is_enabled
            row.recipients_scope = scope_json
            row.updated_at = datetime.utcnow()
        else:
            row = TelegramBusinessConnection(
                user_id=business_user_id,
                connection_id=connection_id,
                business_user_id=business_user_id,
                user_chat_id=user_chat_id,
                is_disabled=not is_enabled,
                recipients_scope=scope_json,
            )
            session.add(row)
    except Exception as e:
        logger.exception("Failed to persist business_connection: %s", e)
