"""
Обработчики раздела «💰 Лимиты по дням» в карточке профиля.

Суточные лимиты (руб) по дням недели Пн–Вс, сохранение в копейках.
Кнопки: применить на сегодня / применить сейчас (на завтра).
"""
import logging
from datetime import date, timedelta

from aiogram import Router, F
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from bot.keyboards import WEEKDAY_NAMES, daily_limits_kb
from bot.states import DailyLimitsStates
from core.daily_limits_runner import apply_daily_limit_for_profile
from core.database.models import AvitoProfile, ProfileDailyLimits
from core.database.session import get_session

logger = logging.getLogger(__name__)
router = Router(name="daily_limits")

PENNY_ATTRS = [
    "mon_penny", "tue_penny", "wed_penny", "thu_penny",
    "fri_penny", "sat_penny", "sun_penny",
]


async def get_profile_and_limits(
    profile_id: int, telegram_id: int, session: AsyncSession
) -> tuple[AvitoProfile | None, ProfileDailyLimits | None]:
    """Профиль и запись лимитов (создаётся при отсутствии)."""
    r = await session.execute(
        select(AvitoProfile)
        .where(AvitoProfile.id == profile_id, AvitoProfile.owner_id == telegram_id)
        .options(selectinload(AvitoProfile.daily_limits))
    )
    profile = r.scalar_one_or_none()
    if not profile:
        return None, None
    limits = profile.daily_limits
    if limits is None:
        limits = ProfileDailyLimits(profile_id=profile_id)
        session.add(limits)
        await session.flush()
    return profile, limits


def format_limits_text(limits: ProfileDailyLimits) -> str:
    """Текст: Пн X р, Вт Y р, ... (из копеек в рубли)."""
    parts = []
    for i, name in enumerate(WEEKDAY_NAMES):
        penny = getattr(limits, PENNY_ATTRS[i], 0) or 0
        rub = penny // 100
        parts.append(f"{name} {rub} р")
    return " | ".join(parts)


def limits_screen_message(limits: ProfileDailyLimits) -> str:
    mode_label = "AUTO (суточный бюджет)" if (limits.mode or "auto_budget") != "manual" else "MANUAL (суточный лимит)"
    return (
        "💰 <b>Лимиты по дням</b>\n\n"
        f"Текущие лимиты (руб/день):\n{format_limits_text(limits)}\n\n"
        f"Режим: {mode_label}\n"
        "Выберите день для изменения или используйте быстрые действия."
    )


@router.callback_query(F.data.startswith("profile_daily_limits:"))
async def cb_open_daily_limits(callback: CallbackQuery, session: AsyncSession) -> None:
    """Открыть экран «Лимиты по дням»."""
    profile_id = int(callback.data.split(":")[1])
    profile, limits = await get_profile_and_limits(profile_id, callback.from_user.id, session)
    if not profile or not limits:
        await callback.answer("Профиль не найден", show_alert=True)
        return
    mode = limits.mode or "auto_budget"
    text = limits_screen_message(limits)
    await callback.message.edit_text(text, reply_markup=daily_limits_kb(profile_id, mode))
    await callback.answer()


@router.callback_query(F.data.startswith("limits_day:"))
async def cb_limits_day(callback: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    """Выбор дня для ввода лимита."""
    parts = callback.data.split(":")
    profile_id = int(parts[1])
    day = int(parts[2])
    if day < 0 or day > 6:
        await callback.answer("Неверный день", show_alert=True)
        return
    profile, limits = await get_profile_and_limits(profile_id, callback.from_user.id, session)
    if not profile or not limits:
        await callback.answer("Профиль не найден", show_alert=True)
        return
    await state.set_state(DailyLimitsStates.waiting_rub)
    await state.update_data(profile_id=profile_id, day=day, action=None)
    day_name = WEEKDAY_NAMES[day]
    await callback.message.edit_text(
        f"Введите лимит на <b>{day_name}</b> в рублях (целое число). 0 = выключить."
    )
    await callback.answer()


@router.callback_query(F.data.startswith("limits_quick_same:"))
async def cb_limits_quick_same(callback: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    """Сделать все дни одинаковыми — запросить одно значение."""
    profile_id = int(callback.data.split(":")[1])
    profile, limits = await get_profile_and_limits(profile_id, callback.from_user.id, session)
    if not profile or not limits:
        await callback.answer("Профиль не найден", show_alert=True)
        return
    await state.set_state(DailyLimitsStates.waiting_rub)
    await state.update_data(profile_id=profile_id, day=None, action="quick_same")
    await callback.message.edit_text(
        "Введите один лимит в рублях для всех дней (целое число ≥ 0). 0 = выключить."
    )
    await callback.answer()


@router.callback_query(F.data.startswith("limits_quick_copy_mon:"))
async def cb_limits_quick_copy_mon(callback: CallbackQuery, session: AsyncSession) -> None:
    """Скопировать лимит понедельника на все дни."""
    profile_id = int(callback.data.split(":")[1])
    profile, limits = await get_profile_and_limits(profile_id, callback.from_user.id, session)
    if not profile or not limits:
        await callback.answer("Профиль не найден", show_alert=True)
        return
    val = limits.mon_penny
    for attr in PENNY_ATTRS[1:]:
        setattr(limits, attr, val)
    text = limits_screen_message(limits)
    await callback.message.edit_text(text, reply_markup=daily_limits_kb(profile_id, limits.mode or "auto_budget"))
    await callback.answer("Пн скопирован на все дни")


@router.callback_query(F.data.startswith("limits_quick_clear:"))
async def cb_limits_quick_clear(callback: CallbackQuery, session: AsyncSession) -> None:
    """Очистить все дни (0)."""
    profile_id = int(callback.data.split(":")[1])
    profile, limits = await get_profile_and_limits(profile_id, callback.from_user.id, session)
    if not profile or not limits:
        await callback.answer("Профиль не найден", show_alert=True)
        return
    for attr in PENNY_ATTRS:
        setattr(limits, attr, 0)
    text = limits_screen_message(limits)
    await callback.message.edit_text(text, reply_markup=daily_limits_kb(profile_id, limits.mode or "auto_budget"))
    await callback.answer("Все лимиты сброшены в 0")


@router.callback_query(F.data.startswith("limits_mode:"))
async def cb_limits_mode(callback: CallbackQuery, session: AsyncSession) -> None:
    """Переключить режим AUTO / MANUAL."""
    parts = callback.data.split(":")
    profile_id = int(parts[1])
    new_mode = parts[2]
    profile, limits = await get_profile_and_limits(profile_id, callback.from_user.id, session)
    if not profile or not limits:
        await callback.answer("Профиль не найден", show_alert=True)
        return
    limits.mode = new_mode
    text = limits_screen_message(limits)
    await callback.message.edit_text(text, reply_markup=daily_limits_kb(profile_id, new_mode))
    await callback.answer()


async def _apply_and_reply(
    callback: CallbackQuery, profile_id: int, telegram_id: int, target_date: date
) -> None:
    ok, err, messages = await apply_daily_limit_for_profile(profile_id, target_date)
    if not messages and ok == 0 and err == 0:
        await callback.answer("Нет активных объявлений для применения лимита.", show_alert=True)
        return
    if messages:
        err_text = "\n".join(messages[:5])
        if len(messages) > 5:
            err_text += f"\n… и ещё {len(messages) - 5}"
        await callback.answer(f"Ошибки: {err_text}", show_alert=True)
    else:
        await callback.answer(f"Применено: {ok} объявлений. Ошибок: {err}", show_alert=(err > 0))


@router.callback_query(F.data.startswith("limits_apply_today:"))
async def cb_limits_apply_today(callback: CallbackQuery, session: AsyncSession) -> None:
    """Применить лимит на сегодня ко всем объявлениям профиля."""
    profile_id = int(callback.data.split(":")[1])
    profile, limits = await get_profile_and_limits(profile_id, callback.from_user.id, session)
    if not profile or not limits:
        await callback.answer("Профиль не найден", show_alert=True)
        return
    await callback.answer("Применяю лимит на сегодня…")
    await _apply_and_reply(callback, profile_id, callback.from_user.id, date.today())
    text = limits_screen_message(limits)
    await callback.message.edit_text(text, reply_markup=daily_limits_kb(profile_id, limits.mode or "auto_budget"))


@router.callback_query(F.data.startswith("limits_apply_now:"))
async def cb_limits_apply_now(callback: CallbackQuery, session: AsyncSession) -> None:
    """Применить лимит на завтра (как job в 23:59)."""
    profile_id = int(callback.data.split(":")[1])
    profile, limits = await get_profile_and_limits(profile_id, callback.from_user.id, session)
    if not profile or not limits:
        await callback.answer("Профиль не найден", show_alert=True)
        return
    tomorrow = date.today() + timedelta(days=1)
    await callback.answer("Применяю лимит на завтра…")
    await _apply_and_reply(callback, profile_id, callback.from_user.id, tomorrow)
    text = limits_screen_message(limits)
    await callback.message.edit_text(text, reply_markup=daily_limits_kb(profile_id, limits.mode or "auto_budget"))


@router.message(DailyLimitsStates.waiting_rub, F.text)
async def process_limits_rub(message: Message, state: FSMContext, session: AsyncSession) -> None:
    """Ввод лимита в рублях (целое ≥ 0)."""
    data = await state.get_data()
    profile_id = data.get("profile_id")
    day = data.get("day")
    action = data.get("action")
    if profile_id is None:
        await state.clear()
        await message.answer("Сессия сброшена. Откройте снова «Лимиты по дням».", reply_markup=None)
        return

    raw = message.text.strip()
    try:
        rub = int(raw)
    except ValueError:
        await message.answer("Введите целое число (рубли). 0 = выключить.")
        return
    if rub < 0:
        await message.answer("Число должно быть ≥ 0.")
        return
    penny = rub * 100

    profile, limits = await get_profile_and_limits(profile_id, message.from_user.id, session)
    if not profile or not limits:
        await state.clear()
        await message.answer("Профиль не найден.")
        return

    if action == "quick_same":
        for attr in PENNY_ATTRS:
            setattr(limits, attr, penny)
        await state.clear()
        text = limits_screen_message(limits)
        await message.answer(text, reply_markup=daily_limits_kb(profile_id, limits.mode or "auto_budget"))
        return

    if day is not None and 0 <= day <= 6:
        setattr(limits, PENNY_ATTRS[day], penny)
    await state.clear()
    text = limits_screen_message(limits)
    await message.answer(text, reply_markup=daily_limits_kb(profile_id, limits.mode or "auto_budget"))
