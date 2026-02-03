"""
APScheduler: AsyncIOScheduler + SQLAlchemyJobStore.

- SQLAlchemyJobStore MUST use a synchronous driver (no postgresql+asyncpg).
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

# Sync URL for SQLAlchemyJobStore: replace '+asyncpg' with '' -> standard postgresql://
_url = settings.DATABASE_URL
if "+asyncpg" in _url:
    _jobstore_url = _url.replace("+asyncpg", "")
elif "sqlite" in _url:
    _jobstore_url = _url.replace("+aiosqlite", "").replace("sqlite+aiosqlite", "sqlite")
else:
    _jobstore_url = _url


def _mask_url(url: str) -> str:
    """Mask password in URL for logging."""
    try:
        from urllib.parse import urlparse, urlunparse
        p = urlparse(url)
        if p.password:
            netloc = p.hostname or ""
            if p.port:
                netloc += f":{p.port}"
            if p.username:
                netloc = f"{p.username}:****@{netloc}"
            else:
                netloc = f"****@{netloc}"
            return urlunparse((p.scheme, netloc, p.path or "", "", "", ""))
    except Exception:
        return url[:50] + "..." if len(url) > 50 else "***"


logger.info("Scheduler JobStore using sync URL: %s", _mask_url(_jobstore_url))

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
