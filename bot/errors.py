"""
Глобальный обработчик ошибок: уведомление админа при ошибке обновления токена Avito.
"""
import logging

from aiogram import Bot
from aiogram.types import ErrorEvent

from core.config import settings

logger = logging.getLogger(__name__)


def _is_token_refresh_error(exception: BaseException) -> bool:
    """Проверка, связана ли ошибка с обновлением токена Avito."""
    msg = str(exception).lower()
    if "token" in msg or "avito" in msg or "401" in msg or "oauth" in msg:
        return True
    if "api.avito.ru" in msg or "token" in msg:
        return True
    return False


async def global_error_handler(event: ErrorEvent, bot: Bot) -> None:
    """
    Логирует ошибку и при ошибке обновления токена Avito отправляет уведомление админу.
    """
    exception = event.exception
    logger.exception("Update %s caused error: %s", event.update, exception)

    admin_chat_id = getattr(settings, "ADMIN_CHAT_ID", None)
    if not admin_chat_id:
        return

    if _is_token_refresh_error(exception):
        try:
            await bot.send_message(
                admin_chat_id,
                "⚠️ <b>Ошибка обновления токена Avito</b>\n\n"
                f"<code>{exception!s}</code>",
            )
        except Exception as e:
            logger.warning("Failed to notify admin: %s", e)
