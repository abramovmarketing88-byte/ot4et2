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
