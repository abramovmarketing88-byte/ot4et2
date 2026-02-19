"""
Handlers для управления профилями Avito.

/add_profile — FSM добавления профиля
/profiles — inline-меню со списком профилей
"""
import logging

from aiogram import Router, F
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.keyboards import (
    profiles_hub_kb,
    profile_hub_kb,
    ai_settings_kb,
    confirm_delete_kb,
    cancel_kb,
)
from bot.states import AddProfileStates, DeleteProfileStates
from core.avito.auth import AvitoAuth
from core.database.models import User, AvitoProfile, AISettings, ScheduledFollowup

logger = logging.getLogger(__name__)
router = Router(name="profiles")


# ═══════════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════════

async def get_user_profiles(telegram_id: int, session: AsyncSession) -> list[AvitoProfile]:
    """Получить все профили пользователя."""
    result = await session.execute(
        select(AvitoProfile).where(AvitoProfile.owner_id == telegram_id)
    )
    return list(result.scalars().all())


async def get_profile_by_id(
    profile_id: int, telegram_id: int, session: AsyncSession
) -> AvitoProfile | None:
    """Получить профиль по ID (с проверкой владельца)."""
    result = await session.execute(
        select(AvitoProfile).where(
            AvitoProfile.id == profile_id,
            AvitoProfile.owner_id == telegram_id,
        )
    )
    return result.scalar_one_or_none()


def format_profile_info(p: AvitoProfile) -> str:
    """Форматирование информации о профиле."""
    status = "✅" if p.user_id else "⏳ не подтверждён"
    return (
        f"<b>{p.profile_name}</b>\n\n"
        f"Avito user_id: <code>{p.user_id or '—'}</code>\n"
        f"Статус: {status}\n"
        f"Токен: {'✅ активен' if p.access_token else '❌ нет'}"
    )


# ═══════════════════════════════════════════════════════════════════════════════
# /profiles — список профилей
# ═══════════════════════════════════════════════════════════════════════════════


async def render_profiles_hub(
    event: Message | CallbackQuery,
    session: AsyncSession,
) -> None:
    """Рендер главного экрана профилей."""
    telegram_id = event.from_user.id
    profiles = await get_user_profiles(telegram_id, session)
    text = "Ваши профили Avito:"
    markup = profiles_hub_kb(profiles)

    if isinstance(event, CallbackQuery):
        await event.message.edit_text(text, reply_markup=markup)
        await event.answer()
    else:
        await event.answer(text, reply_markup=markup)


@router.message(Command("profiles"))
async def cmd_profiles(message: Message, session: AsyncSession) -> None:
    """Показать главный экран профилей."""
    await render_profiles_hub(message, session)


@router.callback_query(F.data == "profiles_back")
async def cb_profiles_back(callback: CallbackQuery, session: AsyncSession) -> None:
    """Вернуться к главному экрану профилей."""
    await render_profiles_hub(callback, session)


@router.callback_query(F.data.startswith("profile_view:"))
async def cb_profile_view(callback: CallbackQuery, session: AsyncSession) -> None:
    """Просмотр профиля."""
    profile_id = int(callback.data.split(":")[1])
    profile = await get_profile_by_id(profile_id, callback.from_user.id, session)
    if not profile:
        await callback.answer("Профиль не найден", show_alert=True)
        return
    await callback.message.edit_text(
        format_profile_info(profile),
        reply_markup=profile_hub_kb(profile_id),
    )
    await callback.answer()


# ═══════════════════════════════════════════════════════════════════════════════
# /add_profile — FSM добавления профиля
# ═══════════════════════════════════════════════════════════════════════════════

@router.message(Command("add_profile"))
@router.callback_query(F.data == "profile_add")
async def cmd_add_profile(event: Message | CallbackQuery, state: FSMContext) -> None:
    """Начать добавление профиля."""
    text = (
        "➕ <b>Добавление профиля Avito</b>\n\n"
        "Введите название профиля (например, «Основной магазин»):"
    )
    if isinstance(event, CallbackQuery):
        await event.message.edit_text(text, reply_markup=cancel_kb())
        await event.answer()
    else:
        await event.answer(text, reply_markup=cancel_kb())
    await state.set_state(AddProfileStates.waiting_profile_name)


@router.message(AddProfileStates.waiting_profile_name, F.text)
async def process_profile_name(message: Message, state: FSMContext) -> None:
    """Получить название профиля."""
    await state.update_data(profile_name=message.text.strip())
    await message.answer(
        "Введите <b>client_id</b> из личного кабинета Avito для бизнеса:",
        reply_markup=cancel_kb(),
    )
    await state.set_state(AddProfileStates.waiting_client_id)


@router.message(AddProfileStates.waiting_client_id, F.text)
async def process_client_id(message: Message, state: FSMContext) -> None:
    """Получить client_id."""
    client_id = message.text.strip()
    if len(client_id) < 10:
        await message.answer("❌ client_id слишком короткий. Попробуйте ещё раз:")
        return
    await state.update_data(client_id=client_id)
    await message.answer(
        "Введите <b>client_secret</b>:",
        reply_markup=cancel_kb(),
    )
    await state.set_state(AddProfileStates.waiting_client_secret)


@router.message(AddProfileStates.waiting_client_secret, F.text)
async def process_client_secret(
    message: Message, state: FSMContext, session: AsyncSession
) -> None:
    """Получить client_secret и валидировать данные."""
    client_secret = message.text.strip()
    if len(client_secret) < 10:
        await message.answer("❌ client_secret слишком короткий. Попробуйте ещё раз:")
        return

    await state.update_data(client_secret=client_secret)
    data = await state.get_data()

    await message.answer("⏳ Проверяю данные и получаю user_id...")

    user_result = await session.execute(
        select(User).where(User.telegram_id == message.from_user.id)
    )
    user = user_result.scalar_one_or_none()
    if not user:
        user = User(telegram_id=message.from_user.id)
        session.add(user)
        await session.flush()

    profile = AvitoProfile(
        owner_id=message.from_user.id,
        profile_name=data["profile_name"],
        client_id=data["client_id"],
        client_secret=client_secret,
    )
    session.add(profile)
    await session.flush()
    await session.refresh(profile)
    await session.commit()

    try:
        auth = AvitoAuth(profile)
        user_id = await auth.get_and_save_user_id()
        await message.answer(
            f"✅ Профиль <b>{data['profile_name']}</b> успешно добавлен!\n\n"
            f"Avito user_id: <code>{user_id}</code>\n\n"
            "Используйте /profiles для настройки отчётов."
        )
    except Exception as e:
        logger.exception("Failed to validate Avito credentials")
        p = await session.get(AvitoProfile, profile.id)
        if p:
            await session.delete(p)
        await message.answer(
            f"❌ Ошибка проверки данных Avito:\n<code>{e}</code>\n\n"
            "Проверьте client_id и client_secret и попробуйте снова: /add_profile"
        )

    await state.clear()


# ═══════════════════════════════════════════════════════════════════════════════
# Удаление профиля
# ═══════════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data.startswith("profile_delete:"))
async def cb_profile_delete(callback: CallbackQuery, session: AsyncSession) -> None:
    """Запрос подтверждения удаления."""
    profile_id = int(callback.data.split(":")[1])
    profile = await get_profile_by_id(profile_id, callback.from_user.id, session)
    if not profile:
        await callback.answer("Профиль не найден", show_alert=True)
        return
    await callback.message.edit_text(
        f"⚠️ Вы уверены, что хотите удалить профиль <b>{profile.profile_name}</b>?\n\n"
        "Все связанные отчёты также будут удалены.",
        reply_markup=confirm_delete_kb(profile_id),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("profile_delete_confirm:"))
async def cb_profile_delete_confirm(
    callback: CallbackQuery, session: AsyncSession
) -> None:
    """Подтверждение удаления профиля."""
    profile_id = int(callback.data.split(":")[1])
    profile = await session.get(AvitoProfile, profile_id)
    if profile and profile.owner_id == callback.from_user.id:
        profile_name = profile.profile_name
        await session.delete(profile)
        await callback.message.edit_text(
            f"✅ Профиль <b>{profile_name}</b> удалён."
        )
    else:
        await callback.message.edit_text("❌ Профиль не найден.")
    await callback.answer()


# ═══════════════════════════════════════════════════════════════════════════════
# Export Messenger to Excel (Account section)
# ═══════════════════════════════════════════════════════════════════════════════


@router.callback_query(F.data.startswith("export_messenger:"))
async def cb_export_messenger(
    callback: CallbackQuery, session: AsyncSession
) -> None:
    """Собрать чаты Avito Messenger и отправить Excel-файл пользователю."""
    profile_id = int(callback.data.split(":")[1])
    profile = await get_profile_by_id(profile_id, callback.from_user.id, session)
    if not profile:
        await callback.answer("Профиль не найден", show_alert=True)
        return
    if not profile.user_id:
        await callback.answer(
            "Сначала завершите настройку профиля (получен user_id Avito).",
            show_alert=True,
        )
        return

    await callback.answer("Формирую выгрузку чатов…")
    status_msg = await callback.message.answer("⏳ Загружаю чаты и сообщения из Avito…")

    try:
        from core.avito.auth import AvitoAuth
        from core.avito.client import AvitoClient
        from utils.formatter import export_chats_to_excel
        from aiogram.types import BufferedInputFile

        auth = AvitoAuth(profile)
        token = await auth.ensure_token()
        client = AvitoClient(token)
        user_id = profile.user_id

        # Список чатов (может быть пагинация — берём первый блок)
        conv = await client.get_conversations(user_id, limit=100, offset=0)
        chats = conv.get("chats") or conv.get("resources") or []
        if isinstance(chats, dict):
            chats = [chats]

        chats_data = []
        for ch in chats:
            chat_id = ch.get("id") or ch.get("chat_id")
            if chat_id is None:
                continue
            context = ch.get("context") or {}
            value = context.get("value", {}) if isinstance(context, dict) else {}
            chat_name = value.get("title") or value.get("id") or str(chat_id)
            last_msg = ch.get("last_message") or {}
            if isinstance(last_msg, dict):
                content = last_msg.get("content") or {}
                last_text = content.get("text") or content.get("message") or ""
                last_created = last_msg.get("created") or last_msg.get("date")
            else:
                last_text = ""
                last_created = None

            try:
                msg_resp = await client.get_messages(user_id, chat_id, limit=100, offset=0)
                messages = msg_resp.get("messages") or msg_resp.get("resources") or []
                if isinstance(messages, dict):
                    messages = [messages]
            except Exception:
                messages = []

            chats_data.append({
                "chat_name": chat_name,
                "last_message": last_text,
                "date": last_created,
                "all_messages": messages,
            })

        if not chats_data:
            await status_msg.edit_text(
                "📭 Чатов не найдено или API не вернул данные. "
                "Проверьте доступ к Messenger API и область прав (scope)."
            )
            return

        buf = export_chats_to_excel(chats_data)
        file_bytes = buf.read()
        document = BufferedInputFile(file_bytes, filename="avito_messenger_chats.xlsx")
        await callback.bot.send_document(
            chat_id=callback.message.chat.id,
            document=document,
            caption=f"📤 Выгрузка чатов Avito: {profile.profile_name}",
        )
        await status_msg.edit_text("✅ Файл отправлен выше.")
    except Exception as e:
        logger.exception("Export messenger failed for profile id=%s", profile_id)
        await status_msg.edit_text(
            f"❌ Ошибка выгрузки: <code>{e!s}</code>\n\n"
            "Проверьте доступ к Messenger API (scope) и наличие чатов."
        )


# ═══════════════════════════════════════════════════════════════════════════════
# Отмена FSM
# ═══════════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data == "cancel")
async def cb_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    """Отмена текущего действия."""
    await state.clear()
    await callback.message.edit_text("❌ Действие отменено.")
    await callback.answer()


@router.message(Command("cancel"), StateFilter("*"))
async def cmd_cancel(message: Message, state: FSMContext) -> None:
    """Отмена по команде."""
    current_state = await state.get_state()
    if current_state is None:
        await message.answer("Нет активного действия для отмены.")
        return
    await state.clear()
    await message.answer("❌ Действие отменено.")


@router.callback_query(F.data.startswith("profile_ai:"))
async def cb_profile_ai(callback: CallbackQuery, session: AsyncSession) -> None:
    profile_id = int(callback.data.split(":")[1])
    profile = await get_profile_by_id(profile_id, callback.from_user.id, session)
    if not profile:
        await callback.answer("Профиль не найден", show_alert=True)
        return
    ai = await session.get(AISettings, profile_id)
    if ai is None:
        ai = AISettings(profile_id=profile_id)
        session.add(ai)
        await session.flush()
    await callback.message.edit_text("🤖 Настройки AI", reply_markup=ai_settings_kb(profile_id, ai.is_enabled))
    await callback.answer()


@router.callback_query(F.data.startswith("profile_ai_toggle:"))
async def cb_profile_ai_toggle(callback: CallbackQuery, session: AsyncSession) -> None:
    profile_id = int(callback.data.split(":")[1])
    profile = await get_profile_by_id(profile_id, callback.from_user.id, session)
    if not profile:
        await callback.answer("Профиль не найден", show_alert=True)
        return
    ai = await session.get(AISettings, profile_id)
    if ai is None:
        ai = AISettings(profile_id=profile_id, is_enabled=True)
        session.add(ai)
    else:
        ai.is_enabled = not ai.is_enabled
    if not ai.is_enabled:
        rows = await session.execute(select(ScheduledFollowup).where(ScheduledFollowup.profile_id == profile_id, ScheduledFollowup.status == "pending"))
        for item in rows.scalars().all():
            item.status = "canceled"
    await callback.message.edit_text("🤖 Настройки AI", reply_markup=ai_settings_kb(profile_id, ai.is_enabled))
    await callback.answer()


@router.callback_query(F.data.startswith("profile_ai_menu:"))
async def cb_profile_ai_menu(callback: CallbackQuery) -> None:
    _, profile_id, section = callback.data.split(":", 2)
    await callback.answer()
    await callback.message.answer(f"Раздел {section} для профиля #{profile_id} пока работает в текстовом режиме. Используйте /prompts для шаблонов.")
