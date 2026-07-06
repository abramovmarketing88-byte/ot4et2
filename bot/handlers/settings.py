"""
Настройка времени и частоты отчётов.

- Report Frequency: подменю [Daily, Every X days, Weekly (выбор дней), Monthly].
- Set Time: FSM ввод HH:MM (обработка в reports.py, кнопка здесь).
"""
import logging
import re

from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession

from bot.handlers.reports import get_profile_by_id
from bot.keyboards import (
    report_frequency_kb,
    report_days_kb,
    report_settings_kb,
    cancel_kb,
)
from bot.states import SettingsStates
from core.database.models import AvitoProfile
from core.scheduler import sync_scheduler_tasks

logger = logging.getLogger(__name__)
router = Router(name="settings")


def _parse_weekdays(weekdays: str | None) -> set[int]:
    """Из строки '0,2,4' получить множество int 0..6."""
    if not weekdays or not weekdays.strip():
        return set()
    result = set()
    for part in weekdays.strip().split(","):
        part = part.strip()
        if part.isdigit():
            d = int(part)
            if 0 <= d <= 6:
                result.add(d)
    return result


def _format_weekdays(days: set[int]) -> str | None:
    """Из множества 0..6 получить строку '0,2,4'."""
    if not days:
        return None
    return ",".join(str(d) for d in sorted(days))


# ═══════════════════════════════════════════════════════════════════════════════
# Report Frequency menu
# ═══════════════════════════════════════════════════════════════════════════════


@router.callback_query(F.data.startswith("report_frequency:"))
async def cb_report_frequency(
    callback: CallbackQuery, session: AsyncSession
) -> None:
    """Открыть подменю частоты отчёта."""
    profile_id = int(callback.data.split(":")[1])
    profile = await get_profile_by_id(profile_id, callback.from_user.id, session)
    if not profile:
        await callback.answer("Профиль не найден", show_alert=True)
        return
    current = getattr(profile, "report_frequency", "daily") or "daily"
    await callback.message.edit_text(
        "🔄 <b>Частота отчёта</b>\n\n"
        "Выберите вариант:\n"
        "• <b>Ежедневно</b> — каждый день в заданное время\n"
        "• <b>Каждые N дней</b> — раз в N дней\n"
        "• <b>Еженедельно</b> — в выбранные дни недели\n"
        "• <b>Ежемесячно</b> — раз в месяц",
        reply_markup=report_frequency_kb(profile_id, current),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("freq_set:"))
async def cb_freq_set(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession
) -> None:
    """Выбор варианта частоты: daily, interval, weekly, monthly."""
    parts = callback.data.split(":")
    profile_id = int(parts[1])
    freq = parts[2]
    profile = await get_profile_by_id(profile_id, callback.from_user.id, session)
    if not profile:
        await callback.answer("Профиль не найден", show_alert=True)
        return

    if freq == "daily":
        profile.report_frequency = "daily"
        profile.report_interval_value = None
        await session.commit()
        await sync_scheduler_tasks()
        await callback.message.edit_text(
            "✅ Частота: <b>ежедневно</b>.\n\nИспользуйте «Настроить отчёт» для других настроек.",
            reply_markup=report_settings_kb(profile_id),
        )
        await callback.answer()
        return

    if freq == "monthly":
        profile.report_frequency = "monthly"
        profile.report_interval_value = None
        await session.commit()
        await sync_scheduler_tasks()
        await callback.message.edit_text(
            "✅ Частота: <b>ежемесячно</b>.\n\nИспользуйте «Настроить отчёт» для других настроек.",
            reply_markup=report_settings_kb(profile_id),
        )
        await callback.answer()
        return

    if freq == "interval":
        await state.update_data(profile_id=profile_id)
        await state.set_state(SettingsStates.waiting_interval_value)
        await callback.message.edit_text(
            "📅 <b>Каждые N дней</b>\n\nВведите число дней (например, <code>3</code> для раз в 3 дня):",
            reply_markup=cancel_kb(),
        )
        await callback.answer()
        return

    if freq == "weekly":
        profile.report_frequency = "weekly"
        await session.commit()
        await sync_scheduler_tasks()
        selected = _parse_weekdays(getattr(profile, "report_weekdays", None))
        await callback.message.edit_text(
            "📅 <b>Еженедельно</b>\n\nВыберите дни недели (Пн = 0, Вс = 6):",
            reply_markup=report_days_kb(profile_id, selected),
        )
        await callback.answer()
        return

    await callback.answer()


@router.message(SettingsStates.waiting_interval_value, F.text)
async def process_interval_value(
    message: Message, state: FSMContext, session: AsyncSession
) -> None:
    """Ввод N для «каждые N дней»."""
    text = message.text.strip()
    if not text.isdigit() or int(text) < 1:
        await message.answer("❌ Введите целое число больше 0 (например, 3):")
        return
    n = int(text)
    if n > 365:
        await message.answer("❌ Укажите число не больше 365:")
        return

    data = await state.get_data()
    profile_id = data.get("profile_id")
    if not profile_id:
        await message.answer("❌ Ошибка. Начните заново: /profiles → Настроить отчёт")
        await state.clear()
        return

    profile = await get_profile_by_id(profile_id, message.from_user.id, session)
    if not profile:
        await message.answer("❌ Профиль не найден.")
        await state.clear()
        return

    profile.report_frequency = "interval"
    profile.report_interval_value = n
    await session.commit()
    await sync_scheduler_tasks()
    await state.clear()
    await message.answer(
        f"✅ Частота: <b>каждые {n} дн.</b>\n\nРасписание обновлено. Используйте /profiles для других настроек."
    )


@router.callback_query(F.data.startswith("report_day_toggle:"))
async def cb_report_day_toggle(
    callback: CallbackQuery, session: AsyncSession
) -> None:
    """Переключение дня недели для еженедельного отчёта."""
    parts = callback.data.split(":")
    profile_id = int(parts[1])
    day = int(parts[2])
    profile = await get_profile_by_id(profile_id, callback.from_user.id, session)
    if not profile:
        await callback.answer("Профиль не найден", show_alert=True)
        return
    profile.report_frequency = "weekly"
    current = _parse_weekdays(getattr(profile, "report_weekdays", None))
    if day in current:
        current.discard(day)
    else:
        current.add(day)
    profile.report_weekdays = _format_weekdays(current)
    selected = _parse_weekdays(profile.report_weekdays)
    await session.commit()
    await sync_scheduler_tasks()
    await callback.message.edit_text(
        "📅 <b>Еженедельно</b>\n\nВыберите дни недели (Пн = 0, Вс = 6):",
        reply_markup=report_days_kb(profile_id, selected),
    )
    await callback.answer()


# ═══════════════════════════════════════════════════════════════════════════════
# /settings command
# ═══════════════════════════════════════════════════════════════════════════════


@router.message(lambda m: m.text and m.text.strip() == "/settings")
async def cmd_settings(message: Message) -> None:
    """Команда /settings — подсказка перейти в профили."""
    await message.answer(
        "⚙️ <b>Настройки отчётов</b>\n\n"
        "Используйте <b>/profiles</b> → выберите профиль → <b>Настроить отчёт</b>, "
        "чтобы задать частоту, время и чат для отчётов."
    )
