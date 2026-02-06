print(">>> DEBUG: PYTHON SCRIPT STARTED")
import sys
import logging
print(">>> DEBUG: PYTHON SCRIPT STARTED (stderr)", file=sys.stderr, flush=True)
logging.basicConfig(stream=sys.stdout, level=logging.DEBUG, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)
logger.info(">>> DEBUG: LOGGING INITIALIZED")

"""
Точка входа: фоновый worker (Telegram long-polling бот), БД, планировщик.
Работает непрерывно до явной остановки. Поддерживает retry, таймауты и корректное завершение по SIGTERM/SIGINT.
"""
import asyncio
import signal

# Логирование уже настроено в самом начале файла

# Константы по умолчанию для worker (переопределяются из core.config.settings)
DEFAULT_STARTUP_TIMEOUT_SEC = 60
DEFAULT_STARTUP_RETRIES = 5
DEFAULT_POLLING_RETRIES = 10
DEFAULT_RETRY_BACKOFF_BASE_SEC = 5
DEFAULT_RETRY_BACKOFF_MAX_SEC = 300

# Глобальный флаг запроса остановки (SIGTERM/SIGINT)
_shutdown_event: asyncio.Event | None = None


def _get_shutdown_event() -> asyncio.Event:
    global _shutdown_event
    if _shutdown_event is None:
        _shutdown_event = asyncio.Event()
    return _shutdown_event


def _request_shutdown() -> None:
    ev = _get_shutdown_event()
    ev.set()
    logger.info("Получен сигнал остановки, запланировано корректное завершение.")


# Импорты приложения после настройки логов
try:
    from aiogram import Bot, Dispatcher
    from aiogram.client.default import DefaultBotProperties
    from aiogram.enums import ParseMode
    from aiogram.types import BotCommand

    from bot.errors import global_error_handler
    from bot.handlers.register import router as register_router
    from bot.handlers.profiles import router as profiles_router
    from bot.handlers.reports import router as reports_router
    from bot.handlers.settings import router as settings_router
    from bot.middleware import DbSessionMiddleware
    from core.database.session import async_engine, init_db
    from core.scheduler import start_scheduler, stop_scheduler
except Exception as e:
    print(f">>> DEBUG: IMPORT ERROR: {e}", flush=True)
    logger.exception("Failed during module imports")
    sys.exit(1)

BOT_COMMANDS = [
    BotCommand(command="start", description="Запуск и список команд"),
    BotCommand(command="add_profile", description="Добавить профиль Avito"),
    BotCommand(command="profiles", description="Управление профилями и отчётами"),
    BotCommand(command="settings", description="Настройка времени и частоты отчётов"),
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
    logger.info("DATABASE_URL (async): %s", _mask_db_url(settings.DATABASE_URL))
    await bot.set_my_commands(BOT_COMMANDS)
    await init_db()
    await start_scheduler(bot)
    logger.info("Бот запущен, планировщик активен.")


async def on_shutdown(bot: Bot) -> None:
    """Остановка планировщика и закрытие соединений."""
    await stop_scheduler()
    await async_engine.dispose()
    logger.info("Бот остановлен, соединения закрыты.")


def _worker_config():
    """Конфигурация worker из env (с fallback)."""
    try:
        from core.config import settings
        return (
            getattr(settings, "WORKER_STARTUP_TIMEOUT_SEC", DEFAULT_STARTUP_TIMEOUT_SEC),
            getattr(settings, "WORKER_STARTUP_RETRIES", DEFAULT_STARTUP_RETRIES),
            getattr(settings, "WORKER_POLLING_RETRIES", DEFAULT_POLLING_RETRIES),
            getattr(settings, "WORKER_RETRY_BACKOFF_BASE_SEC", DEFAULT_RETRY_BACKOFF_BASE_SEC),
            getattr(settings, "WORKER_RETRY_BACKOFF_MAX_SEC", DEFAULT_RETRY_BACKOFF_MAX_SEC),
        )
    except Exception:
        return (
            DEFAULT_STARTUP_TIMEOUT_SEC,
            DEFAULT_STARTUP_RETRIES,
            DEFAULT_POLLING_RETRIES,
            DEFAULT_RETRY_BACKOFF_BASE_SEC,
            DEFAULT_RETRY_BACKOFF_MAX_SEC,
        )


async def _startup_with_timeout(bot: Bot) -> None:
    """Выполнить on_startup с общим таймаутом."""
    timeout, *_ = _worker_config()
    await asyncio.wait_for(on_startup(bot), timeout=timeout)


async def _create_bot_and_dispatcher():
    """Создать Bot и Dispatcher, зарегистрировать handlers и lifecycle."""
    from core.config import settings

    bot = Bot(
        token=settings.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher()
    dp["bot"] = bot

    dp.update.middleware(DbSessionMiddleware())

    async def error_handler(event: object) -> None:
        await global_error_handler(event, bot)

    dp.errors.register(error_handler)
    dp.include_router(register_router)
    dp.include_router(profiles_router)
    dp.include_router(reports_router)
    dp.include_router(settings_router)
    # Startup вызывается явно до start_polling; shutdown — при отмене задачи или при ошибке
    dp.shutdown.register(on_shutdown)

    return bot, dp


async def _run_polling_until_shutdown(bot: Bot, dp: Dispatcher) -> None:
    """
    Запустить long polling. Работает до отмены задачи (SIGTERM/SIGINT) или ошибки.
    (delete_webhook выполняется в фазе startup.)
    """
    try:
        logger.info("Starting bot...")
        logger.info("Диспетчер запущен, переход в режим long polling (worker работает непрерывно).")
        await dp.start_polling(bot)
    except Exception as e:
        print(f">>> DEBUG: CRITICAL STARTUP ERROR: {str(e)}")
        logger.exception("Bot failed to start")
        sys.exit(1)


async def _backoff_sleep(attempt: int, phase: str) -> None:
    """Ожидание с экспоненциальным backoff перед повтором."""
    _, _, _, base_sec, max_sec = _worker_config()
    delay = min(base_sec * (2 ** (attempt - 1)), max_sec)
    logger.info("Повтор через %s с (фаза: %s, попытка %s).", delay, phase, attempt)
    await asyncio.sleep(delay)


async def run_worker_with_backoff() -> None:
    """Обёртка: backoff при старте и при падении polling — асинхронный sleep."""
    shutdown = _get_shutdown_event()
    _, startup_retries, polling_retries, _, _ = _worker_config()
    startup_attempt = 0
    polling_attempt = 0

    while not shutdown.is_set():
        bot = None
        dp = None

        while startup_attempt < startup_retries and not shutdown.is_set():
            startup_attempt += 1
            try:
                logger.info("Инициализация бота и диспетчера (попытка %s/%s)...", startup_attempt, startup_retries)
                bot, dp = await _create_bot_and_dispatcher()
                await _startup_with_timeout(bot)
                await asyncio.wait_for(
                    bot.delete_webhook(drop_pending_updates=True),
                    timeout=30,
                )
                logger.info("Старт успешен, запуск long polling.")
                startup_attempt = 0  # сброс для следующего цикла после падения polling
                break
            except asyncio.TimeoutError as e:
                logger.warning("Таймаут при запуске (попытка %s): %s", startup_attempt, e)
                if bot:
                    await on_shutdown(bot)
                await _backoff_sleep(startup_attempt, "startup")
            except Exception as e:
                logger.exception("Ошибка при запуске (попытка %s): %s", startup_attempt, e)
                if bot:
                    try:
                        await on_shutdown(bot)
                    except Exception:
                        pass
                await _backoff_sleep(startup_attempt, "startup")
        else:
            if shutdown.is_set():
                logger.info("Остановка запрошена до завершения запуска.")
                return
            logger.error("Исчерпаны попытки запуска (%s), выход.", startup_retries)
            sys.exit(1)

        polling_task = None
        try:
            polling_task = asyncio.create_task(_run_polling_until_shutdown(bot, dp))
            done, _ = await asyncio.wait(
                [polling_task, asyncio.create_task(shutdown.wait())],
                return_when=asyncio.FIRST_COMPLETED,
            )
            if shutdown.is_set():
                logger.info("Запрос остановки, отмена long polling...")
                if polling_task and not polling_task.done():
                    polling_task.cancel()
                    try:
                        await polling_task
                    except asyncio.CancelledError:
                        pass
                return
            if polling_task.done() and polling_task.cancelled():
                return
            if polling_task.done() and polling_task.exception():
                raise polling_task.exception()
        except asyncio.CancelledError:
            if polling_task and not polling_task.done():
                polling_task.cancel()
                try:
                    await polling_task
                except asyncio.CancelledError:
                    pass
            return
        except Exception as e:
            polling_attempt += 1
            logger.exception("Long polling завершился с ошибкой (попытка %s/%s): %s", polling_attempt, polling_retries, e)
            try:
                await on_shutdown(bot)
            except Exception:
                pass
            if polling_attempt >= polling_retries:
                logger.error("Исчерпаны попытки polling (%s), выход.", polling_retries)
                sys.exit(1)
            await _backoff_sleep(polling_attempt, "polling")


def main() -> None:
    """Точка входа: регистрация сигналов и запуск worker loop."""
    logger.info("Worker запускается (непрерывный режим до SIGTERM/SIGINT).")
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    try:
        loop.add_signal_handler(signal.SIGTERM, _request_shutdown)
    except NotImplementedError:
        pass  # Windows
    try:
        loop.add_signal_handler(signal.SIGINT, _request_shutdown)
    except NotImplementedError:
        pass

    try:
        loop.run_until_complete(run_worker_with_backoff())
    except KeyboardInterrupt:
        logger.info("Получен KeyboardInterrupt.")
    finally:
        _get_shutdown_event().set()
        loop.close()
    logger.info("Worker завершён.")


if __name__ == "__main__":
    main()
