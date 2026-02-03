"""
Handler для команды /start.
"""
from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.database.models import User

router = Router(name="register")


async def get_or_create_user(telegram_id: int, session: AsyncSession) -> User:
    """Получить или создать пользователя по telegram_id (использует сессию из middleware)."""
    result = await session.execute(
        select(User).where(User.telegram_id == telegram_id)
    )
    user = result.scalar_one_or_none()
    if user:
        return user
    user = User(telegram_id=telegram_id)
    session.add(user)
    await session.flush()
    await session.refresh(user)
    return user


@router.message(CommandStart())
async def cmd_start(message: Message, session: AsyncSession) -> None:
    """Приветствие и регистрация пользователя."""
    telegram_id = message.from_user.id if message.from_user else 0
    await get_or_create_user(telegram_id, session)
    await message.answer(
        "👋 <b>Добро пожаловать в Avito Analytics Bot!</b>\n\n"
        "Этот бот поможет вам получать статистику по объявлениям Avito.\n\n"
        "<b>Команды:</b>\n"
        "/add_profile — добавить профиль Avito\n"
        "/profiles — управление профилями\n"
        "/stats — в группе/канале: получить отчёт в этот чат (сначала настройте чат здесь)\n"
        "/cancel — отменить текущее действие"
    )
