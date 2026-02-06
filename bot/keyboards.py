"""Inline и Reply клавиатуры."""
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from core.database.models import AvitoProfile


def profiles_list_kb(profiles: list[AvitoProfile]) -> InlineKeyboardMarkup:
    """Список профилей с кнопками управления."""
    builder = InlineKeyboardBuilder()
    for p in profiles:
        # Кнопка с названием профиля
        builder.row(
            InlineKeyboardButton(
                text=f"📊 {p.profile_name}",
                callback_data=f"profile_view:{p.id}",
            )
        )
    builder.row(
        InlineKeyboardButton(text="➕ Добавить профиль", callback_data="profile_add")
    )
    return builder.as_markup()


def profile_actions_kb(profile_id: int) -> InlineKeyboardMarkup:
    """Кнопки действий для профиля."""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="📈 Настроить отчёт",
            callback_data=f"profile_report:{profile_id}",
        ),
        InlineKeyboardButton(
            text="🗑 Удалить",
            callback_data=f"profile_delete:{profile_id}",
        ),
    )
    builder.row(
        InlineKeyboardButton(text="« Назад", callback_data="profiles_back")
    )
    return builder.as_markup()


def confirm_delete_kb(profile_id: int) -> InlineKeyboardMarkup:
    """Подтверждение удаления."""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="✅ Да, удалить",
            callback_data=f"profile_delete_confirm:{profile_id}",
        ),
        InlineKeyboardButton(
            text="❌ Отмена",
            callback_data=f"profile_view:{profile_id}",
        ),
    )
    return builder.as_markup()


def report_settings_kb(profile_id: int) -> InlineKeyboardMarkup:
    """Настройки отчёта."""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="📤 Получить отчёт сейчас",
            callback_data=f"report_now:{profile_id}",
        )
    )
    builder.row(
        InlineKeyboardButton(
            text="📋 Настроить характеристики",
            callback_data=f"report_characteristics:{profile_id}",
        )
    )
    builder.row(
        InlineKeyboardButton(
            text="💬 Установить чат",
            callback_data=f"report_set_chat:{profile_id}",
        )
    )
    builder.row(
        InlineKeyboardButton(
            text="🕐 Установить время",
            callback_data=f"report_set_time:{profile_id}",
        )
    )
    builder.row(
        InlineKeyboardButton(text="« Назад", callback_data=f"profile_view:{profile_id}")
    )
    return builder.as_markup()


def report_characteristics_kb(
    profile_id: int, selected_keys: set[str]
) -> InlineKeyboardMarkup:
    """Выбор характеристик отчёта: вкл/выкл (все по умолчанию = все включены)."""
    from utils.analytics import ALL_REPORT_METRIC_KEYS, REPORT_METRIC_LABELS

    builder = InlineKeyboardBuilder()
    # Показать все = пустой report_metrics → считаем все выбранными
    all_selected = len(selected_keys) == 0
    for key in ALL_REPORT_METRIC_KEYS:
        label = REPORT_METRIC_LABELS.get(key, key)
        on = all_selected or key in selected_keys
        prefix = "✅" if on else "⬜"
        builder.row(
            InlineKeyboardButton(
                text=f"{prefix} {label}",
                callback_data=f"report_toggle:{profile_id}:{key}",
            )
        )
    builder.row(
        InlineKeyboardButton(
            text="✅ Включить все",
            callback_data=f"report_metrics_all:{profile_id}",
        ),
        InlineKeyboardButton(
            text="« Назад",
            callback_data=f"profile_report:{profile_id}",
        )
    )
    return builder.as_markup()


def set_chat_kb(profile_id: int) -> InlineKeyboardMarkup:
    """Выбор способа установки chat_id."""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="📍 Использовать этот чат",
            callback_data=f"report_chat_here:{profile_id}",
        )
    )
    builder.row(
        InlineKeyboardButton(
            text="↩️ Переслать сообщение из чата",
            callback_data=f"report_chat_forward:{profile_id}",
        )
    )
    builder.row(
        InlineKeyboardButton(text="« Отмена", callback_data=f"profile_report:{profile_id}")
    )
    return builder.as_markup()


def cancel_kb() -> InlineKeyboardMarkup:
    """Кнопка отмены."""
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="❌ Отмена", callback_data="cancel"))
    return builder.as_markup()


# ═══════════════════════════════════════════════════════════════════════════
# Выбор дат / дней (для настроек расписания и периодов)
# ═══════════════════════════════════════════════════════════════════════════

WEEKDAY_LABELS = ("Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс")


def report_days_kb(profile_id: int, selected_days: set[int]) -> InlineKeyboardMarkup:
    """
    Инлайновое меню выбора дней недели (0=Пн .. 6=Вс).
    selected_days: множество 0..6; пустое = все дни.
    """
    builder = InlineKeyboardBuilder()
    all_selected = len(selected_days) == 0
    for day in range(7):
        on = all_selected or day in selected_days
        prefix = "✅" if on else "⬜"
        builder.row(
            InlineKeyboardButton(
                text=f"{prefix} {WEEKDAY_LABELS[day]}",
                callback_data=f"report_day_toggle:{profile_id}:{day}",
            )
        )
    builder.row(
        InlineKeyboardButton(
            text="« Назад",
            callback_data=f"profile_report:{profile_id}",
        )
    )
    return builder.as_markup()


def report_period_kb(profile_id: int, current: str = "day") -> InlineKeyboardMarkup:
    """Выбор периода отчёта: день / неделя / месяц."""
    builder = InlineKeyboardBuilder()
    for period, label in (("day", "День"), ("week", "Неделя"), ("month", "Месяц")):
        prefix = "✅" if period == current else "⬜"
        builder.row(
            InlineKeyboardButton(
                text=f"{prefix} {label}",
                callback_data=f"report_period:{profile_id}:{period}",
            )
        )
    builder.row(
        InlineKeyboardButton(
            text="« Назад",
            callback_data=f"profile_report:{profile_id}",
        )
    )
    return builder.as_markup()
