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


def profiles_hub_kb(profiles: list[AvitoProfile]) -> InlineKeyboardMarkup:
    """Главный экран профилей из основного меню."""
    builder = InlineKeyboardBuilder()
    for p in profiles:
        builder.row(
            InlineKeyboardButton(
                text=f"📊 {p.profile_name}",
                callback_data=f"profile_view:{p.id}",
            )
        )
    builder.row(
        InlineKeyboardButton(text="➕ Добавить профиль", callback_data="profile_add")
    )
    builder.row(InlineKeyboardButton(text="⬅ Назад", callback_data="main:menu"))
    return builder.as_markup()


def reports_profiles_kb(profiles: list[AvitoProfile]) -> InlineKeyboardMarkup:
    """Выбор профиля для перехода в настройки отчётов."""
    builder = InlineKeyboardBuilder()
    for p in profiles:
        builder.row(
            InlineKeyboardButton(
                text=f"📊 {p.profile_name}",
                callback_data=f"profile_report:{p.id}",
            )
        )
    builder.row(InlineKeyboardButton(text="👤 Профили", callback_data="main:profiles"))
    builder.row(InlineKeyboardButton(text="⬅ Назад", callback_data="main:menu"))
    return builder.as_markup()


def reports_no_profiles_kb() -> InlineKeyboardMarkup:
    """Кнопки для экрана отчётов, когда профилей нет."""
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="➕ Добавить профиль", callback_data="profile_add"))
    builder.row(InlineKeyboardButton(text="👤 Профили", callback_data="main:profiles"))
    builder.row(InlineKeyboardButton(text="⬅ Назад", callback_data="main:menu"))
    return builder.as_markup()


def profile_actions_kb(profile_id: int) -> InlineKeyboardMarkup:
    """Кнопки действий для профиля (Account section)."""
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
        InlineKeyboardButton(
            text="📤 Экспорт Messenger в Excel",
            callback_data=f"export_messenger:{profile_id}",
        )
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
            text="📅 Исторический отчёт",
            callback_data=f"report_historical:{profile_id}",
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
            text="🔄 Частота отчёта",
            callback_data=f"report_frequency:{profile_id}",
        ),
        InlineKeyboardButton(
            text="🕐 Установить время",
            callback_data=f"report_set_time:{profile_id}",
        )
    )
    builder.row(
        InlineKeyboardButton(
            text="💬 Установить чат",
            callback_data=f"report_set_chat:{profile_id}",
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
# Частота отчёта (Report Frequency submenu)
# ═══════════════════════════════════════════════════════════════════════════


def report_frequency_kb(profile_id: int, current: str = "daily") -> InlineKeyboardMarkup:
    """Подменю частоты: Daily, Every X days, Weekly, Monthly."""
    builder = InlineKeyboardBuilder()
    for freq, label in (
        ("daily", "Ежедневно"),
        ("interval", "Каждые N дней"),
        ("weekly", "Еженедельно (выбор дней)"),
        ("monthly", "Ежемесячно"),
    ):
        prefix = "✅" if freq == current else "⬜"
        builder.row(
            InlineKeyboardButton(
                text=f"{prefix} {label}",
                callback_data=f"freq_set:{profile_id}:{freq}",
            )
        )
    builder.row(
        InlineKeyboardButton(
            text="« Назад",
            callback_data=f"profile_report:{profile_id}",
        )
    )
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


def mode_select_kb(current_mode: str = "reports") -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    ai_prefix = "✅" if current_mode == "ai_seller" else "⬜"
    rep_prefix = "✅" if current_mode == "reports" else "⬜"
    builder.row(InlineKeyboardButton(text=f"{ai_prefix} ИИ-продавец", callback_data="ai_mode:set:ai_seller"))
    builder.row(InlineKeyboardButton(text=f"{rep_prefix} Отчётность", callback_data="ai_mode:set:reports"))
    return builder.as_markup()


def ai_branches_kb(branches: list[tuple[int, str]], current_branch_id: int | None = None) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for branch_id, name in branches:
        prefix = "✅" if current_branch_id == branch_id else "⬜"
        builder.row(
            InlineKeyboardButton(
                text=f"{prefix} {name}",
                callback_data=f"ai_branch:select:{branch_id}",
            )
        )
    builder.row(InlineKeyboardButton(text="↩️ К режимам", callback_data="ai_mode:menu"))
    return builder.as_markup()


def ai_admin_menu_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🧩 Шаблоны промптов", callback_data="ai_admin:prompts"))
    builder.row(InlineKeyboardButton(text="🌿 AI-ветки", callback_data="ai_admin:branches"))
    builder.row(InlineKeyboardButton(text="⏰ Фоллоу-апы", callback_data="ai_admin:followups"))
    return builder.as_markup()


def start_main_menu_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="📊 Отчёты", callback_data="main:reports"))
    builder.row(InlineKeyboardButton(text="🤖 AI-продавец", callback_data="main:ai"))
    builder.row(InlineKeyboardButton(text="👤 Профили", callback_data="main:profiles"))
    builder.row(InlineKeyboardButton(text="🔌 Каналы / Интеграции", callback_data="main:integrations"))
    builder.row(InlineKeyboardButton(text="⚙ Глобальные AI-шаблоны", callback_data="main:templates"))
    builder.row(InlineKeyboardButton(text="❓ Помощь", callback_data="main:help"))
    return builder.as_markup()


def integrations_menu_kb() -> InlineKeyboardMarkup:
    """Экран выбора канала интеграции."""
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🟦 Avito", callback_data="intg:avito"))
    builder.row(InlineKeyboardButton(text="✈️ Telegram", callback_data="intg:telegram"))
    builder.row(InlineKeyboardButton(text="⬅ Назад", callback_data="main:menu"))
    return builder.as_markup()


def telegram_integration_kb() -> InlineKeyboardMarkup:
    """Экран Telegram: бот, business, тест, назад."""
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🤖 Подключить Telegram-бота", callback_data="tg_int:bot"))
    builder.row(InlineKeyboardButton(text="👤 Подключить личный аккаунт (Telegram Business)", callback_data="tg_int:business"))
    builder.row(InlineKeyboardButton(text="📄 Тест отправки", callback_data="tg_int:test_send"))
    builder.row(InlineKeyboardButton(text="⬅ Назад", callback_data="intg:back"))
    return builder.as_markup()


def telegram_bot_target_kb(target_id: int | None) -> InlineKeyboardMarkup:
    """Кнопки для настройки целевого чата (bot mode)."""
    builder = InlineKeyboardBuilder()
    if target_id is not None:
        builder.row(InlineKeyboardButton(text="✏️ Ввести chat_id", callback_data=f"tg_target:input_chat:{target_id}"))
        builder.row(InlineKeyboardButton(text="📩 Переслать сообщение из чата", callback_data=f"tg_target:forward:{target_id}"))
        builder.row(InlineKeyboardButton(text="📝 Тестовое сообщение", callback_data=f"tg_target:welcome_msg:{target_id}"))
    else:
        builder.row(InlineKeyboardButton(text="✏️ Ввести chat_id", callback_data="tg_target:input_chat:0"))
        builder.row(InlineKeyboardButton(text="📩 Переслать сообщение из чата", callback_data="tg_target:forward:0"))
    builder.row(InlineKeyboardButton(text="⬅ Назад", callback_data="intg:telegram"))
    return builder.as_markup()


def telegram_business_status_kb() -> InlineKeyboardMarkup:
    """Кнопки экрана статуса Business."""
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="⬅ Назад", callback_data="intg:telegram"))
    return builder.as_markup()


def profile_hub_kb(profile_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="📊 Настройки отчёта", callback_data=f"profile_report:{profile_id}"))
    builder.row(InlineKeyboardButton(text="🤖 Настройки AI", callback_data=f"profile_ai:{profile_id}"))
    builder.row(InlineKeyboardButton(text="🗑 Удалить", callback_data=f"profile_delete:{profile_id}"))
    builder.row(InlineKeyboardButton(text="⬅ Назад", callback_data="profiles_back"))
    return builder.as_markup()


def ai_settings_kb(profile_id: int, enabled: bool) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for text, action in (
        ("🧠 Промпт", "prompt"),
        ("📩 Фоллоу-апы", "followups"),
        ("🚦 Антиспам", "antispam"),
        ("🛑 Стоп-слова", "stopwords"),
        ("👥 Сотрудники", "employees"),
        ("📄 Сводка", "summary"),
        ("📊 Лимиты", "limits"),
    ):
        builder.row(InlineKeyboardButton(text=text, callback_data=f"profile_ai_menu:{profile_id}:{action}"))
    toggle = "🔌 Выключить AI" if enabled else "🔌 Включить AI"
    builder.row(InlineKeyboardButton(text=toggle, callback_data=f"profile_ai_toggle:{profile_id}"))
    builder.row(InlineKeyboardButton(text="⬅ Назад", callback_data=f"profile_view:{profile_id}"))
    return builder.as_markup()


def ai_profile_hub_kb(profile_id: int, _profile_name: str, enabled: bool) -> InlineKeyboardMarkup:
    """Хаб настроек ИИ: 13 кнопок по ТЗ."""
    builder = InlineKeyboardBuilder()
    for text, action in (
        ("🧠 Основной промпт", "prompt"),
        ("📚 Контекст диалога", "context"),
        ("✍ Формат сообщений", "format"),
        ("⏳ Задержка ответа", "delay"),
        ("📩 Фоллоу-апы", "followups"),
        ("🚦 Ограничения", "limits"),
        ("🛑 Стоп-слова", "stopwords"),
        ("👥 Чат уведомлений", "notify_chat"),
        ("🔄 Передача управления", "handoff"),
        ("🤖 Модель", "model"),
    ):
        builder.row(InlineKeyboardButton(text=text, callback_data=f"ai_set:{action}:{profile_id}"))
    toggle = "🔌 Выключить AI" if enabled else "🔌 Включить AI"
    builder.row(InlineKeyboardButton(text=toggle, callback_data=f"ai_set:toggle:{profile_id}"))
    builder.row(InlineKeyboardButton(text="💬 Тест-чат", callback_data=f"ai_profile:test_chat:{profile_id}"))
    builder.row(InlineKeyboardButton(text="⬅ Назад", callback_data="ai_profile:back_to_list"))
    return builder.as_markup()


def _back_to_hub(profile_id: int) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="⬅ Назад", callback_data=f"ai_set:back_hub:{profile_id}"))
    return b.as_markup()


def ai_set_prompt_kb(profile_id: int) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="✏️ Редактировать", callback_data=f"ai_set:prompt_edit:{profile_id}"))
    b.row(InlineKeyboardButton(text="📚 Выбрать из шаблонов", callback_data=f"ai_set:prompt_tpl:{profile_id}"))
    b.row(InlineKeyboardButton(text="📂 Загрузить .txt файл", callback_data=f"ai_set:prompt_file:{profile_id}"))
    b.row(InlineKeyboardButton(text="⬅ Назад", callback_data=f"ai_set:back_hub:{profile_id}"))
    return b.as_markup()


def ai_set_context_kb(profile_id: int) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="☑ Весь контекст", callback_data=f"ai_set:ctx_all:{profile_id}"))
    b.row(InlineKeyboardButton(text="🔢 Последние N сообщений", callback_data=f"ai_set:ctx_lastn:{profile_id}"))
    b.row(InlineKeyboardButton(text="⏱ За последние N часов", callback_data=f"ai_set:ctx_hours:{profile_id}"))
    b.row(InlineKeyboardButton(text="⬅ Назад", callback_data=f"ai_set:back_hub:{profile_id}"))
    return b.as_markup()


def ai_set_format_kb(profile_id: int) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="☑ Одним сообщением", callback_data=f"ai_set:fmt_single:{profile_id}"))
    b.row(InlineKeyboardButton(text="🔢 Разбивать по N предложений", callback_data=f"ai_set:fmt_sentences:{profile_id}"))
    b.row(InlineKeyboardButton(text="⬅ Назад", callback_data=f"ai_set:back_hub:{profile_id}"))
    return b.as_markup()


def ai_set_delay_kb(profile_id: int) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="✏️ Изменить (секунды)", callback_data=f"ai_set:delay_edit:{profile_id}"))
    b.row(InlineKeyboardButton(text="⬅ Назад", callback_data=f"ai_set:back_hub:{profile_id}"))
    return b.as_markup()


def ai_set_limits_kb(profile_id: int) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="📨 Макс сообщений в диалоге", callback_data=f"ai_set:limit_dialog:{profile_id}"))
    b.row(InlineKeyboardButton(text="📅 Макс диалогов в день", callback_data=f"ai_set:limit_daily:{profile_id}"))
    b.row(InlineKeyboardButton(text="⏳ Мин пауза между ответами (сек)", callback_data=f"ai_set:limit_pause:{profile_id}"))
    b.row(InlineKeyboardButton(text="⬅ Назад", callback_data=f"ai_set:back_hub:{profile_id}"))
    return b.as_markup()


def ai_set_stopwords_kb(profile_id: int) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="✏️ Задать список (через запятую)", callback_data=f"ai_set:stopwords_edit:{profile_id}"))
    b.row(InlineKeyboardButton(text="⬅ Назад", callback_data=f"ai_set:back_hub:{profile_id}"))
    return b.as_markup()


def ai_set_notify_chat_kb(profile_id: int) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="📩 Переслать сообщение из чата", callback_data=f"ai_set:notify_forward:{profile_id}"))
    b.row(InlineKeyboardButton(text="⬅ Назад", callback_data=f"ai_set:back_hub:{profile_id}"))
    return b.as_markup()


def ai_set_handoff_kb(profile_id: int) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="☑ Останавливать ИИ при сообщении сотрудника", callback_data=f"ai_set:handoff_toggle_stop:{profile_id}"))
    b.row(InlineKeyboardButton(text="☑ Авто-возврат управления ИИ", callback_data=f"ai_set:handoff_toggle_return:{profile_id}"))
    b.row(InlineKeyboardButton(text="⏱ Время возврата (минуты)", callback_data=f"ai_set:handoff_minutes:{profile_id}"))
    b.row(InlineKeyboardButton(text="⬅ Назад", callback_data=f"ai_set:back_hub:{profile_id}"))
    return b.as_markup()


def ai_set_model_kb(profile_id: int) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="🤖 gpt-4o-mini (единственный)", callback_data=f"ai_set:model_confirm:{profile_id}"))
    b.row(InlineKeyboardButton(text="⬅ Назад", callback_data=f"ai_set:back_hub:{profile_id}"))
    return b.as_markup()


def profiles_for_ai_kb(
    profiles: list[AvitoProfile],
    current_profile_id: int | None = None,
) -> InlineKeyboardMarkup:
    """Клавиатура выбора профиля в ИИ-режиме (те же профили, что и в /profiles)."""
    builder = InlineKeyboardBuilder()
    for p in profiles:
        prefix = "✅" if current_profile_id == p.id else "⬜"
        builder.row(
            InlineKeyboardButton(
                text=f"{prefix} 📊 {p.profile_name}",
                callback_data=f"ai_profile:select:{p.id}",
            )
        )
    builder.row(InlineKeyboardButton(text="⬅ Назад", callback_data="ai_mode:menu"))
    return builder.as_markup()
