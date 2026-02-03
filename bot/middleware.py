"""
Middleware: одна сессия БД на один апдейт.
"""
import logging
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject
from sqlalchemy.ext.asyncio import AsyncSession

from core.database.session import get_session

logger = logging.getLogger(__name__)


class DbSessionMiddleware(BaseMiddleware):
    """
    Открывает сессию БД на время обработки апдейта и передаёт её в data["session"].
    Все хендлеры получают один и тот же session для запроса.
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        async with get_session() as session:
            data["session"] = session
            return await handler(event, data)
