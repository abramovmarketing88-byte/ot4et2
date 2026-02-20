"""FSM-состояния для сценариев бота."""
from aiogram.fsm.state import State, StatesGroup


class AddProfileStates(StatesGroup):
    """Добавление профиля Avito."""
    waiting_profile_name = State()
    waiting_client_id = State()
    waiting_client_secret = State()
    validating = State()


class ConfigureReportStates(StatesGroup):
    """Настройка отчёта для профиля."""
    choosing_profile = State()
    waiting_chat_id = State()
    waiting_time = State()


class DeleteProfileStates(StatesGroup):
    """Удаление профиля."""
    confirm_delete = State()


class SettingsStates(StatesGroup):
    """Настройка времени, частоты и периода отчёта."""
    choosing_time = State()
    choosing_days = State()
    choosing_period = State()
    waiting_interval = State()
    waiting_interval_value = State()  # для "Every X days"


class HistoricalReportStates(StatesGroup):
    """Исторический отчёт: ввод периода."""
    waiting_start_date = State()
    waiting_end_date = State()


class AiSellerStates(StatesGroup):
    choosing_branch = State()
    chatting = State()


class PromptAdminStates(StatesGroup):
    waiting_name = State()
    waiting_scope = State()
    waiting_content = State()
    editing_prompt = State()
    confirming_delete = State()


class BranchAdminStates(StatesGroup):
    waiting_name = State()
    waiting_avito_profile_id = State()
    waiting_gpt_model = State()
    waiting_system_prompt_id = State()
    waiting_context_retention_days = State()
    waiting_max_messages_in_context = State()
    waiting_followup_enabled = State()


class FollowupAdminStates(StatesGroup):
    # Chain
    waiting_branch_id = State()
    waiting_name = State()
    waiting_start_event = State()
    waiting_stop_on_conversion = State()
    waiting_is_active = State()
    # Step
    waiting_order_index = State()
    waiting_delay_seconds = State()
    waiting_send_mode = State()
    waiting_content_type = State()
    waiting_fixed_text = State()
    waiting_prompt_template_id = State()
    waiting_target_channel = State()


class AiSettingsStates(StatesGroup):
    """Ввод значений в настройках ИИ по профилю."""
    waiting_prompt_text = State()
    waiting_context_value = State()
    waiting_message_sentences = State()
    waiting_delay_seconds = State()
    waiting_limit_value = State()
    waiting_stop_words = State()
    waiting_forward_for_chat = State()
    waiting_auto_return_minutes = State()
    waiting_min_pause = State()


class TelegramIntegrationStates(StatesGroup):
    """Telegram интеграция: целевой чат и тестовое сообщение."""
    waiting_chat_id = State()
    waiting_forward = State()
    waiting_welcome_message = State()


class DailyLimitsStates(StatesGroup):
    """Лимиты по дням: ввод лимита в рублях для выбранного дня."""
    waiting_rub = State()
