"""
APScheduler: AsyncIOScheduler + SQLAlchemyJobStore.

- Инициализация с DATABASE_URL проекта (sync URL для JobStore).
- Джоб раз в минуту: проверка ReportTask и запуск отчётов при совпадении report_time.
- Часовой пояс: Europe/Moscow.
"""
import logging
from typing import Optional

from aiogram import Bot
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from core.config import settings
from core.report_runner import check_report_tasks, set_report_bot

logger = logging.getLogger(__name__)

TIMEZONE = "Europe/Moscow"

# Sync URL для SQLAlchemyJobStore
_url = settings.DATABASE_URL
if "sqlite" in _url:
    _jobstore_url = _url.replace("+aiosqlite", "").replace("sqlite+aiosqlite", "sqlite")
else:
    _jobstore_url = _url.replace("+asyncpg", "+psycopg2")

jobstores = {
    "default": SQLAlchemyJobStore(url=_jobstore_url),
}

scheduler: Optional[AsyncIOScheduler] = None


def get_scheduler() -> AsyncIOScheduler:
    global scheduler
    if scheduler is None:
        scheduler = AsyncIOScheduler(
            jobstores=jobstores,
            timezone=TIMEZONE,
        )
    return scheduler


async def start_scheduler(bot: Bot) -> None:
    """Запуск планировщика и добавление джоба проверки отчётов."""
    set_report_bot(bot)
    s = get_scheduler()
    if s.running:
        return
    # Джоб раз в минуту: проверяет ReportTask (bot берётся из set_report_bot)
    s.add_job(
        check_report_tasks,
        "interval",
        minutes=1,
        id="report_tasks_check",
        replace_existing=True,
    )
    s.start()
    logger.info("Scheduler started (timezone=%s).", TIMEZONE)


async def stop_scheduler() -> None:
    global scheduler
    if scheduler and scheduler.running:
        scheduler.shutdown(wait=False)
        scheduler = None
        logger.info("Scheduler stopped.")
