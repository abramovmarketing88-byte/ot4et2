"""
Handlers для настройки отчётов.

- Настройка chat_id (через кнопку или пересылку)
- Настройка времени отчёта
- Настройка характеристик отчёта (какие метрики отправлять)
"""
import json
import logging
import re

from aiogram import Router, F
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from bot.keyboards import report_settings_kb, report_characteristics_kb, set_chat_kb, cancel_kb
from bot.states import ConfigureReportStates, HistoricalReportStates
from core.database.models import AvitoProfile, ReportTask
from core.report_runner import run_combined_report_to_chat, run_report_to_chat
from core.scheduler import sync_scheduler_tasks

logger = logging.getLogger(__name__)
router = Router(name="reports")


# ═══════════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════════

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


async def get_or_create_report_task(
    profile_id: int, session: AsyncSession
) -> ReportTask:
    """Получить или создать задачу отчёта для профиля."""
    result = await session.execute(
        select(ReportTask).where(ReportTask.profile_id == profile_id)
    )
    task = result.scalar_one_or_none()
    if task:
        return task
    task = ReportTask(profile_id=profile_id, chat_id=0, report_time="10:00")
    session.add(task)
    await session.flush()
    await session.refresh(task)
    return task


def format_report_settings(profile: AvitoProfile, task: ReportTask | None) -> str:
    """Форматирование настроек отчёта."""
    from utils.analytics import ALL_REPORT_METRIC_KEYS, REPORT_METRIC_LABELS

    if not task:
        return (
            f"📈 <b>Настройки отчёта: {profile.profile_name}</b>\n\n"
            "Отчёт не настроен."
        )
    chat_status = f"<code>{task.chat_id}</code>" if task.chat_id else "не указан"
    active_status = "✅ активен" if task.is_active else "⏸ приостановлен"
    selected = _parse_report_metrics(task.report_metrics)
    total = len(ALL_REPORT_METRIC_KEYS)
    if not selected:
        char_line = f"Характеристики: все ({total}) — просмотры, контакты, расходы, кошелёк, аванс и др."
    else:
        labels = [REPORT_METRIC_LABELS.get(k, k) for k in ALL_REPORT_METRIC_KEYS if k in selected]
        char_line = f"Характеристики: {len(selected)} из {total} — " + ", ".join(labels[:5])
        if len(labels) > 5:
            char_line += "…"
    return (
        f"📈 <b>Настройки отчёта: {profile.profile_name}</b>\n\n"
        f"Чат: {chat_status}\n"
        f"Время: {task.report_time}\n"
        f"Статус: {active_status}\n"
        f"{char_line}"
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Команда /stats — получить отчёт в этом чате (для групп/каналов)
# ═══════════════════════════════════════════════════════════════════════════════

@router.message(Command("stats"))
async def cmd_stats(message: Message, session: AsyncSession) -> None:
    """
    В группе/канале: отправить отчёт Avito в этот чат.
    Работает только если для этого чата уже настроен отчёт (через бота в ЛС: /profiles → Установить чат).
    """
    chat_id = message.chat.id

    result = await session.execute(
        select(ReportTask)
        .where(ReportTask.chat_id == chat_id)
        .where(ReportTask.profile_id.isnot(None))
        .options(selectinload(ReportTask.profile))
    )
    tasks = list(result.scalars().unique().all())

    if not tasks:
        await message.answer(
            "📊 <b>Статистика по этому чату не настроена.</b>\n\n"
            "Напишите боту в личные сообщения, добавьте профиль Avito и укажите этот чат "
            "для отчётов (<b>/profiles</b> → выберите профиль → <b>Настроить отчёт</b> → <b>Установить чат</b> → "
            "перешлите сюда любое сообщение). После этого команда /stats будет присылать отчёт сюда.",
        )
        return

    sent = await message.answer("📈 Формирую отчёт за вчера…")

    profiles = [task.profile for task in tasks if task.profile]
    selected_metrics = None
    # Для сводного отчёта берём набор характеристик из первой задачи,
    # где характеристики явно заданы.
    for task in tasks:
        if task.report_metrics:
            try:
                selected_metrics = json.loads(task.report_metrics)
                break
            except (TypeError, json.JSONDecodeError):
                selected_metrics = None

    if message.bot:
        await run_combined_report_to_chat(
            message.bot,
            profiles,
            chat_id,
            selected_metrics=selected_metrics,
        )

    try:
        await sent.edit_text("✅ Отчёт отправлен выше.")
    except Exception:
        pass


# ═══════════════════════════════════════════════════════════════════════════════
# Настройки отчёта
# ═══════════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data.startswith("profile_report:"))
async def cb_profile_report(
    callback: CallbackQuery, session: AsyncSession
) -> None:
    """Открыть настройки отчёта."""
    profile_id = int(callback.data.split(":")[1])
    profile = await get_profile_by_id(profile_id, callback.from_user.id, session)
    if not profile:
        await callback.answer("Профиль не найден", show_alert=True)
        return

    result = await session.execute(
        select(ReportTask).where(ReportTask.profile_id == profile_id)
    )
    task = result.scalar_one_or_none()

    await callback.message.edit_text(
        format_report_settings(profile, task),
        reply_markup=report_settings_kb(profile_id),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("report_now:"))
async def cb_report_now(
    callback: CallbackQuery, session: AsyncSession
) -> None:
    """Отправить отчёт за вчера в настроенный чат отчётов (task.chat_id), а не в ЛС с ботом."""
    profile_id = int(callback.data.split(":")[1])
    profile = await get_profile_by_id(profile_id, callback.from_user.id, session)
    if not profile:
        await callback.answer("Профиль не найден", show_alert=True)
        return

    result = await session.execute(
        select(ReportTask).where(ReportTask.profile_id == profile_id)
    )
    task = result.scalar_one_or_none()

    # Отправляем в чат, указанный в настройках отчёта; если не указан — в текущий (ЛС) с предупреждением
    if task and task.chat_id:
        chat_id = task.chat_id
        await callback.answer("Формирую отчёт за вчера… Отправлю в настроенный чат.")
    else:
        chat_id = callback.message.chat.id
        await callback.answer("Формирую отчёт за вчера… Чат для отчётов не указан — отправляю сюда.")

    selected = None
    if task and task.report_metrics:
        try:
            selected = json.loads(task.report_metrics)
        except (TypeError, json.JSONDecodeError):
            pass
    if callback.bot:
        await run_report_to_chat(callback.bot, profile, chat_id, selected_metrics=selected)

    if task and task.chat_id and chat_id != callback.message.chat.id:
        await callback.message.answer("✅ Отчёт отправлен в настроенный чат.")


# ═══════════════════════════════════════════════════════════════════════════════
# Настройка характеристик отчёта
# ═══════════════════════════════════════════════════════════════════════════════

def _parse_report_metrics(report_metrics: str | None) -> set[str]:
    """Из JSON-строки report_metrics получить множество выбранных ключей. Пусто = все."""
    if not report_metrics:
        return set()
    try:
        lst = json.loads(report_metrics)
        return set(lst) if isinstance(lst, list) else set()
    except (TypeError, json.JSONDecodeError):
        return set()


@router.callback_query(F.data.startswith("report_characteristics:"))
async def cb_report_characteristics(
    callback: CallbackQuery, session: AsyncSession
) -> None:
    """Экран выбора характеристик отчёта."""
    profile_id = int(callback.data.split(":")[1])
    profile = await get_profile_by_id(profile_id, callback.from_user.id, session)
    if not profile:
        await callback.answer("Профиль не найден", show_alert=True)
        return
    result = await session.execute(
        select(ReportTask).where(ReportTask.profile_id == profile_id)
    )
    task = result.scalar_one_or_none()
    selected = _parse_report_metrics(task.report_metrics if task else None)
    await callback.message.edit_text(
        "📋 <b>Какие характеристики включать в отчёт</b>\n\n"
        "Нажмите на строку, чтобы включить/выключить. Пустой список = все включены.",
        reply_markup=report_characteristics_kb(profile_id, selected),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("report_toggle:"))
async def cb_report_toggle(
    callback: CallbackQuery, session: AsyncSession
) -> None:
    """Переключить одну характеристику (вкл/выкл)."""
    from utils.analytics import ALL_REPORT_METRIC_KEYS

    parts = callback.data.split(":")
    profile_id = int(parts[1])
    key = parts[2]
    profile = await get_profile_by_id(profile_id, callback.from_user.id, session)
    if not profile:
        await callback.answer("Профиль не найден", show_alert=True)
        return
    result = await session.execute(
        select(ReportTask).where(ReportTask.profile_id == profile_id)
    )
    task = result.scalar_one_or_none()
    if not task:
        task = ReportTask(profile_id=profile_id, chat_id=0, report_time="10:00")
        session.add(task)
        await session.flush()
    selected = _parse_report_metrics(task.report_metrics)
    if not selected:
        selected = set(ALL_REPORT_METRIC_KEYS)
    if key in selected:
        selected.discard(key)
    else:
        selected.add(key)
    task.report_metrics = json.dumps(list(selected)) if selected else None
    await callback.message.edit_text(
        "📋 <b>Какие характеристики включать в отчёт</b>\n\n"
        "Нажмите на строку, чтобы включить/выключить.",
        reply_markup=report_characteristics_kb(profile_id, selected),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("report_metrics_all:"))
async def cb_report_metrics_all(
    callback: CallbackQuery, session: AsyncSession
) -> None:
    """Включить все характеристики (сброс выбора)."""
    profile_id = int(callback.data.split(":")[1])
    result = await session.execute(
        select(ReportTask).where(ReportTask.profile_id == profile_id)
    )
    task = result.scalar_one_or_none()
    if task:
        task.report_metrics = None
    await callback.message.edit_text(
        "📋 <b>Какие характеристики включать в отчёт</b>\n\n"
        "Все характеристики включены. Нажмите на строку, чтобы выключить.",
        reply_markup=report_characteristics_kb(profile_id, set()),
    )
    await callback.answer("Все характеристики включены")


# ═══════════════════════════════════════════════════════════════════════════════
# Установка chat_id
# ═══════════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data.startswith("report_set_chat:"))
async def cb_report_set_chat(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession
) -> None:
    """Показать варианты установки chat_id."""
    profile_id = int(callback.data.split(":")[1])
    profile = await get_profile_by_id(profile_id, callback.from_user.id, session)
    if not profile:
        await callback.answer("Профиль не найден", show_alert=True)
        return

    await state.update_data(profile_id=profile_id)
    await callback.message.edit_text(
        "💬 <b>Установка чата для отчётов</b>\n\n"
        "Выберите способ:\n"
        "• <b>Использовать этот чат</b> — отчёты будут отправляться сюда\n"
        "• <b>Переслать сообщение</b> — перешлите любое сообщение из нужного чата",
        reply_markup=set_chat_kb(profile_id),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("report_chat_here:"))
async def cb_report_chat_here(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession
) -> None:
    """Использовать текущий чат для отчётов."""
    profile_id = int(callback.data.split(":")[1])
    profile = await get_profile_by_id(profile_id, callback.from_user.id, session)
    if not profile:
        await callback.answer("Профиль не найден", show_alert=True)
        return

    chat_id = callback.message.chat.id

    result = await session.execute(
        select(ReportTask).where(ReportTask.profile_id == profile_id)
    )
    task = result.scalar_one_or_none()
    if task:
        task.chat_id = chat_id
    else:
        task = ReportTask(profile_id=profile_id, chat_id=chat_id)
        session.add(task)

    await state.clear()
    await callback.message.edit_text(
        f"✅ Чат установлен: <code>{chat_id}</code>\n\n"
        "Отчёты будут отправляться в этот чат.",
        reply_markup=report_settings_kb(profile_id),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("report_chat_forward:"))
async def cb_report_chat_forward(callback: CallbackQuery, state: FSMContext) -> None:
    """Ожидание пересланного сообщения."""
    profile_id = int(callback.data.split(":")[1])
    await state.update_data(profile_id=profile_id)
    await state.set_state(ConfigureReportStates.waiting_chat_id)
    await callback.message.edit_text(
        "↩️ <b>Перешлите любое сообщение</b> из чата, куда нужно отправлять отчёты.\n\n"
        "Бот должен быть добавлен в этот чат с правами на отправку сообщений.",
        reply_markup=cancel_kb(),
    )
    await callback.answer()


@router.message(ConfigureReportStates.waiting_chat_id, F.forward_from_chat)
async def process_forwarded_from_chat(
    message: Message, state: FSMContext, session: AsyncSession
) -> None:
    """Обработка пересланного сообщения из чата/канала."""
    data = await state.get_data()
    profile_id = data.get("profile_id")
    if not profile_id:
        await message.answer("❌ Ошибка. Начните заново через /profiles")
        await state.clear()
        return

    chat_id = message.forward_from_chat.id

    result = await session.execute(
        select(ReportTask).where(ReportTask.profile_id == profile_id)
    )
    task = result.scalar_one_or_none()
    if task:
        task.chat_id = chat_id
    else:
        task = ReportTask(profile_id=profile_id, chat_id=chat_id)
        session.add(task)

    await state.clear()
    await message.answer(
        f"✅ Чат установлен: <code>{chat_id}</code>\n"
        f"Название: {message.forward_from_chat.title or '—'}\n\n"
        "Используйте /profiles для дальнейшей настройки."
    )


@router.message(ConfigureReportStates.waiting_chat_id, F.forward_from)
async def process_forwarded_from_user(message: Message, state: FSMContext) -> None:
    """Обработка пересланного сообщения от пользователя (ЛС)."""
    await message.answer(
        "⚠️ Это сообщение переслано от пользователя, а не из группы/канала.\n"
        "Перешлите сообщение из группы или канала, куда нужно отправлять отчёты."
    )


@router.message(ConfigureReportStates.waiting_chat_id)
async def process_chat_id_invalid(message: Message) -> None:
    """Некорректный ввод chat_id."""
    await message.answer(
        "⚠️ Перешлите сообщение из чата или канала.\n"
        "Или отправьте /cancel для отмены."
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Установка времени отчёта
# ═══════════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data.startswith("report_set_time:"))
async def cb_report_set_time(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession
) -> None:
    """Запрос времени отчёта."""
    profile_id = int(callback.data.split(":")[1])
    profile = await get_profile_by_id(profile_id, callback.from_user.id, session)
    if not profile:
        await callback.answer("Профиль не найден", show_alert=True)
        return

    await state.update_data(profile_id=profile_id)
    await state.set_state(ConfigureReportStates.waiting_time)
    await callback.message.edit_text(
        "🕐 <b>Установка времени отчёта</b>\n\n"
        "Введите время в формате <b>ЧЧ:ММ</b>\n"
        "Например: <code>09:00</code> или <code>18:30</code>",
        reply_markup=cancel_kb(),
    )
    await callback.answer()


@router.message(ConfigureReportStates.waiting_time, F.text)
async def process_report_time(
    message: Message, state: FSMContext, session: AsyncSession
) -> None:
    """Обработка введённого времени (HH:MM). Обновляет ReportTask и AvitoProfile.report_time."""
    time_text = message.text.strip()

    # Валидация формата ЧЧ:ММ
    if not re.match(r"^([01]?\d|2[0-3]):([0-5]\d)$", time_text):
        await message.answer(
            "❌ Неверный формат времени.\n"
            "Введите в формате <b>ЧЧ:ММ</b> (например, 09:00):"
        )
        return

    # Нормализация (09:00 вместо 9:00)
    hours, minutes = time_text.split(":")
    time_normalized = f"{int(hours):02d}:{minutes}"

    data = await state.get_data()
    profile_id = data.get("profile_id")
    if not profile_id:
        await message.answer("❌ Ошибка. Начните заново через /profiles")
        await state.clear()
        return

    profile = await get_profile_by_id(profile_id, message.from_user.id, session)
    if profile:
        from datetime import time
        profile.report_time = time(int(hours), int(minutes))

    result = await session.execute(
        select(ReportTask).where(ReportTask.profile_id == profile_id)
    )
    task = result.scalar_one_or_none()
    if task:
        task.report_time = time_normalized
    else:
        task = ReportTask(profile_id=profile_id, chat_id=0, report_time=time_normalized)
        session.add(task)

    await session.commit()
    await sync_scheduler_tasks()

    await state.clear()
    await message.answer(
        f"✅ Время отчёта установлено: <b>{time_normalized}</b>\n\n"
        "Расписание обновлено. Используйте /profiles для других настроек."
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Исторический отчёт (Start Date / End Date)
# ═══════════════════════════════════════════════════════════════════════════════


def _parse_yyyy_mm_dd(text: str) -> str | None:
    """Проверка формата YYYY-MM-DD, возвращает нормализованную строку или None."""
    text = text.strip()
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", text):
        return None
    try:
        from datetime import datetime
        datetime.strptime(text, "%Y-%m-%d")
        return text
    except ValueError:
        return None


@router.callback_query(F.data.startswith("report_historical:"))
async def cb_report_historical(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession
) -> None:
    """Запуск FSM ввода периода для исторического отчёта."""
    profile_id = int(callback.data.split(":")[1])
    profile = await get_profile_by_id(profile_id, callback.from_user.id, session)
    if not profile:
        await callback.answer("Профиль не найден", show_alert=True)
        return
    await state.update_data(profile_id=profile_id)
    await state.set_state(HistoricalReportStates.waiting_start_date)
    await callback.message.edit_text(
        "📅 <b>Исторический отчёт</b>\n\n"
        "Введите <b>дату начала</b> периода в формате <b>YYYY-MM-DD</b>\n"
        "Например: <code>2025-01-01</code>",
        reply_markup=cancel_kb(),
    )
    await callback.answer()


@router.message(HistoricalReportStates.waiting_start_date, F.text)
async def process_historical_start_date(
    message: Message, state: FSMContext, session: AsyncSession
) -> None:
    """Приём даты начала периода."""
    start = _parse_yyyy_mm_dd(message.text)
    if not start:
        await message.answer(
            "❌ Неверный формат. Введите дату в формате <b>YYYY-MM-DD</b> (например, 2025-01-01):"
        )
        return
    await state.update_data(start_date=start)
    await state.set_state(HistoricalReportStates.waiting_end_date)
    await message.answer(
        "Введите <b>дату окончания</b> периода в формате <b>YYYY-MM-DD</b>\n"
        "Например: <code>2025-01-31</code>",
        reply_markup=cancel_kb(),
    )


@router.message(HistoricalReportStates.waiting_end_date, F.text)
async def process_historical_end_date(
    message: Message, state: FSMContext, session: AsyncSession
) -> None:
    """Приём даты окончания и запуск отчёта за период."""
    end = _parse_yyyy_mm_dd(message.text)
    if not end:
        await message.answer(
            "❌ Неверный формат. Введите дату в формате <b>YYYY-MM-DD</b>:"
        )
        return
    data = await state.get_data()
    start = data.get("start_date")
    profile_id = data.get("profile_id")
    if not start or not profile_id:
        await message.answer("❌ Ошибка. Начните заново: /profiles → Исторический отчёт")
        await state.clear()
        return
    if end < start:
        await message.answer("❌ Дата окончания должна быть не раньше даты начала.")
        return

    profile = await get_profile_by_id(profile_id, message.from_user.id, session)
    if not profile:
        await message.answer("❌ Профиль не найден.")
        await state.clear()
        return

    result = await session.execute(
        select(ReportTask).where(ReportTask.profile_id == profile_id)
    )
    task = result.scalar_one_or_none()
    chat_id = message.chat.id
    if task and task.chat_id:
        chat_id = task.chat_id

    selected = None
    if task and task.report_metrics:
        try:
            selected = json.loads(task.report_metrics)
        except (TypeError, json.JSONDecodeError):
            pass

    await state.clear()
    sent = await message.answer(f"📈 Формирую исторический отчёт за период {start} – {end}…")

    if message.bot:
        await run_report_to_chat(
            message.bot,
            profile,
            chat_id,
            selected_metrics=selected,
            start_date=start,
            end_date=end,
        )
    try:
        await sent.edit_text("✅ Исторический отчёт отправлен выше.")
    except Exception:
        pass
