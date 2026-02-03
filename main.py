"""
Точка входа: запуск бота, БД, планировщик, middleware и глобальный обработчик ошибок.
"""
import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import BotCommand

from bot.errors import global_error_handler
from bot.handlers.register import router as register_router
from bot.handlers.profiles import router as profiles_router
from bot.handlers.reports import router as reports_router
from bot.middleware import DbSessionMiddleware
from core.database.session import async_engine, init_db
from core.scheduler import start_scheduler, stop_scheduler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)


BOT_COMMANDS = [
    BotCommand(command="start", description="Запуск и список команд"),
    BotCommand(command="add_profile", description="Добавить профиль Avito"),
    BotCommand(command="profiles", description="Управление профилями и отчётами"),
    BotCommand(command="stats", description="В группе: получить отчёт в этот чат"),
    BotCommand(command="cancel", description="Отменить текущее действие"),
]


def _mask_db_url(url: str) -> str:
    """Mask password in DATABASE_URL for logging."""
    try:
        from urllib.parse import urlparse, urlunparse
        p = urlparse(url)
        if p.password:
            netloc = f"{p.username or ''}:****@{p.hostname or ''}" + (f":{p.port}" if p.port else "")
            return urlunparse((p.scheme, netloc, p.path or "", "", "", ""))
    except Exception:
        pass
    return "***"


async def on_startup(bot: Bot) -> None:
    """Инициализация при старте: меню команд, БД и планировщик."""
    from core.config import settings
    logger.info("Bot DATABASE_URL (async): %s", _mask_db_url(settings.DATABASE_URL))
    await bot.set_my_commands(BOT_COMMANDS)
    await init_db()
    await start_scheduler(bot)
    logger.info("Bot started.")


async def on_shutdown(bot: Bot) -> None:
    """Остановка планировщика и закрытие соединений."""
    await stop_scheduler()
    await async_engine.dispose()
    logger.info("Bot stopped.")


async def main() -> None:
    from core.config import settings

    bot = Bot(
        token=settings.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher()
    dp["bot"] = bot

    # Одна сессия БД на апдейт — передаётся в data["session"]
    dp.update.middleware(DbSessionMiddleware())

    # Глобальный обработчик ошибок: уведомление админа при ошибке токена Avito
    async def error_handler(event: object) -> None:
        await global_error_handler(event, bot)

    dp.errors.register(error_handler)

    dp.include_router(register_router)
    dp.include_router(profiles_router)
    dp.include_router(reports_router)

    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
