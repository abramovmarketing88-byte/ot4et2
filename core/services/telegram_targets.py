"""Сервис целевых чатов Telegram (уведомления / тест отправки)."""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.database.models import TelegramTarget


async def get_or_create_target(
    user_id: int, session: AsyncSession
) -> TelegramTarget:
    """Получить или создать один целевой чат для пользователя."""
    r = await session.execute(
        select(TelegramTarget)
        .where(TelegramTarget.user_id == user_id)
        .where(TelegramTarget.is_active == True)
        .limit(1)
    )
    target = r.scalar_one_or_none()
    if target:
        return target
    target = TelegramTarget(user_id=user_id, target_chat_id=0, is_active=True)
    session.add(target)
    await session.flush()
    await session.refresh(target)
    return target


async def get_target_by_id(
    target_id: int, user_id: int, session: AsyncSession
) -> TelegramTarget | None:
    """Получить целевой чат по id с проверкой владельца."""
    r = await session.execute(
        select(TelegramTarget).where(
            TelegramTarget.id == target_id,
            TelegramTarget.user_id == user_id,
        )
    )
    return r.scalar_one_or_none()


async def get_active_target(
    user_id: int, session: AsyncSession
) -> TelegramTarget | None:
    """Получить активный целевой чат с ненулевым target_chat_id."""
    r = await session.execute(
        select(TelegramTarget)
        .where(TelegramTarget.user_id == user_id)
        .where(TelegramTarget.is_active == True)
        .where(TelegramTarget.target_chat_id != 0)
        .limit(1)
    )
    return r.scalar_one_or_none()
