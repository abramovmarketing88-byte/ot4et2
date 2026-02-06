"""
Настройка времени и частоты отчётов.

Обработчики для выбора времени отправки, дней недели и периода отчёта.
"""
from aiogram import Router
from aiogram.types import Message

router = Router(name="settings")


@router.message(lambda m: m.text and m.text.strip() == "/settings")
async def cmd_settings(message: Message) -> None:
    """Команда /settings — переход к настройкам времени и частоты."""
    await message.answer(
        "⚙️ Настройки времени и частоты отчётов.\n"
        "Используйте раздел «Профили» → выберите профиль → «Настроить отчёт» для настройки времени и дней."
    )
