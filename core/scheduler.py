"""
APScheduler: AsyncIOScheduler + SQLAlchemyJobStore.

- SQLAlchemyJobStore MUST use a synchronous driver (no postgresql+asyncpg).
- sync_scheduler_tasks() reads report_frequency, report_time, report_weekdays from DB
  and adds one job per active ReportTask (daily / interval / weekly).
- Часовой пояс по умолчанию: Europe/Moscow; для задач используется profile.report_timezone.
"""
import logging
from datetime import datetime, timedelta
from typing import Optional

from aiogram import Bot
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from zoneinfo import ZoneInfo

from core.config import settings
from core.database.models import AvitoProfile, ReportTask
from core.database.models import AIBranch, AIDialogMessage, AIDialogState, FollowupStep, ScheduledFollowup
from core.database.session import get_session
from core.llm.client import LLMClient
from core.report_runner import run_report, set_report_bot

logger = logging.getLogger(__name__)

TIMEZONE = "Europe/Moscow"
REPORT_JOB_ID_PREFIX = "report_task_"
SYNC_JOB_ID = "report_sync_tasks"
AI_FOLLOWUP_JOB_ID = "ai_followup_processor"

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


async def run_scheduled_report(task_id: int) -> None:
    """
    Запуск отчёта по задаче (вызывается планировщиком по расписанию).
    Загружает task и profile из БД и вызывает run_report.
    """
    from core.report_runner import _current_bot
    bot = _current_bot
    if not bot:
        logger.warning("run_scheduled_report: bot not set, skip task_id=%s", task_id)
        return
    async with get_session() as session:
        result = await session.execute(
            select(ReportTask)
            .where(ReportTask.id == task_id)
            .where(ReportTask.is_active == True)
            .where(ReportTask.chat_id != 0)
            .options(selectinload(ReportTask.profile))
        )
        task = result.scalar_one_or_none()
    if not task or not task.profile:
        logger.debug("run_scheduled_report: task id=%s not found or inactive", task_id)
        return
    profile = task.profile
    if not getattr(profile, "is_report_active", True):
        logger.debug("run_scheduled_report: profile id=%s reports disabled", profile.id)
        return
    try:
        await run_report(bot, task, profile)
    except Exception as e:
        logger.exception("run_scheduled_report failed for task id=%s: %s", task_id, e)


def _tz_or_default(report_timezone: Optional[str]) -> ZoneInfo:
    """Возвращает ZoneInfo для report_timezone или Europe/Moscow по умолчанию."""
    if not report_timezone or not report_timezone.strip():
        return ZoneInfo(TIMEZONE)
    try:
        return ZoneInfo(report_timezone.strip())
    except Exception:
        return ZoneInfo(TIMEZONE)


def _next_run_at_report_time(profile: AvitoProfile) -> datetime:
    """Следующий момент времени = report_time в report_timezone профиля."""
    tz = _tz_or_default(getattr(profile, "report_timezone", None))
    now = datetime.now(tz)
    report_time = getattr(profile, "report_time", None)
    if report_time is None:
        # fallback: 09:00
        hour, minute = 9, 0
    else:
        hour, minute = report_time.hour, report_time.minute
    next_run = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if next_run <= now:
        next_run += timedelta(days=1)
    return next_run


async def sync_scheduler_tasks() -> None:
    """
    Синхронизация джобов с БД: читает report_frequency, report_time, report_weekdays
    из AvitoProfile и создаёт/обновляет джобы для каждой активной ReportTask.

    - daily: каждый день в report_time (часовой пояс профиля).
    - weekly: в report_time в указанные дни недели (report_weekdays, e.g. '0,2,4' = Пн, Ср, Пт).
    - interval: каждые report_interval_value дней в report_time.
    """
    s = get_scheduler()
    if not s.running:
        logger.debug("sync_scheduler_tasks: scheduler not running, skip")
        return

    async with get_session() as session:
        result = await session.execute(
            select(ReportTask)
            .where(ReportTask.is_active == True)
            .where(ReportTask.chat_id != 0)
            .options(selectinload(ReportTask.profile))
        )
        tasks = list(result.scalars().unique().all())

    # Удаляем старые джобы отчётов (по префиксу id)
    for job in s.get_jobs():
        if job.id and job.id.startswith(REPORT_JOB_ID_PREFIX):
            try:
                job.remove()
            except Exception as e:
                logger.debug("Could not remove job %s: %s", job.id, e)

    scheduled = 0
    for task in tasks:
        profile = task.profile
        if not profile:
            continue
        if not getattr(profile, "is_report_active", True):
            continue
        frequency = getattr(profile, "report_frequency", "daily") or "daily"
        tz = _tz_or_default(getattr(profile, "report_timezone", None))
        report_time = getattr(profile, "report_time", None)
        hour = report_time.hour if report_time else 9
        minute = report_time.minute if report_time else 0
        job_id = f"{REPORT_JOB_ID_PREFIX}{task.id}"

        try:
            if frequency == "daily":
                trigger = CronTrigger(
                    hour=hour,
                    minute=minute,
                    timezone=tz,
                )
                s.add_job(
                    run_scheduled_report,
                    trigger=trigger,
                    id=job_id,
                    args=[task.id],
                    replace_existing=True,
                )
                scheduled += 1
            elif frequency == "weekly":
                weekdays = getattr(profile, "report_weekdays", None) or "0,1,2,3,4"
                trigger = CronTrigger(
                    day_of_week=weekdays,
                    hour=hour,
                    minute=minute,
                    timezone=tz,
                )
                s.add_job(
                    run_scheduled_report,
                    trigger=trigger,
                    id=job_id,
                    args=[task.id],
                    replace_existing=True,
                )
                scheduled += 1
            elif frequency == "interval":
                n = getattr(profile, "report_interval_value", None) or 1
                if n < 1:
                    n = 1
                next_run = _next_run_at_report_time(profile)
                trigger = IntervalTrigger(
                    days=n,
                    start_date=next_run,
                    timezone=tz,
                )
                s.add_job(
                    run_scheduled_report,
                    trigger=trigger,
                    id=job_id,
                    args=[task.id],
                    replace_existing=True,
                )
                scheduled += 1
            else:
                # monthly / unknown: treat as daily
                trigger = CronTrigger(hour=hour, minute=minute, timezone=tz)
                s.add_job(
                    run_scheduled_report,
                    trigger=trigger,
                    id=job_id,
                    args=[task.id],
                    replace_existing=True,
                )
                scheduled += 1
        except Exception as e:
            logger.exception("Failed to add job for task id=%s: %s", task.id, e)

    logger.info("sync_scheduler_tasks: scheduled %s report job(s).", scheduled)


async def start_scheduler(bot: Bot) -> None:
    """Запуск планировщика и синхронизация джобов отчётов из БД."""
    set_report_bot(bot)
    s = get_scheduler()
    if s.running:
        return
    s.start()
    logger.info("Scheduler started (timezone=%s).", TIMEZONE)
    await sync_scheduler_tasks()
    # Периодическая пересинхронизация при изменении настроек (каждые 15 мин)
    s.add_job(
        sync_scheduler_tasks,
        "interval",
        minutes=15,
        id=SYNC_JOB_ID,
        replace_existing=True,
    )
    s.add_job(
        process_followups,
        "interval",
        seconds=45,
        id=AI_FOLLOWUP_JOB_ID,
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )


async def process_followups() -> None:
    from core.report_runner import _current_bot

    bot = _current_bot
    if not bot:
        return

    async with get_session() as session:
        result = await session.execute(
            select(ScheduledFollowup)
            .where(ScheduledFollowup.status == "pending")
            .where(ScheduledFollowup.execute_at <= datetime.utcnow())
            .order_by(ScheduledFollowup.execute_at.asc())
            .limit(100)
        )
        items = list(result.scalars().all())

        for item in items:
            try:
                step_res = await session.execute(
                    select(FollowupStep).where(FollowupStep.id == item.step_id)
                )
                step = step_res.scalar_one_or_none()
                if not step:
                    item.status = "failed"
                    continue

                state_res = await session.execute(
                    select(AIDialogState).where(
                        AIDialogState.user_id == item.user_id,
                        AIDialogState.branch_id == item.branch_id,
                        AIDialogState.dialog_id == item.dialog_id,
                    )
                )
                dialog_state = state_res.scalar_one_or_none()
                converted = dialog_state.is_converted if dialog_state else item.converted
                negative = dialog_state.has_negative if dialog_state else item.negative_detected

                if step.send_mode == "if_not_converted" and converted:
                    item.status = "canceled"
                    continue
                if step.send_mode == "if_not_converted_and_no_negative" and (converted or negative):
                    item.status = "canceled"
                    continue

                text = ""
                if step.content_type == "fixed":
                    text = step.fixed_text or ""
                else:
                    branch_res = await session.execute(select(AIBranch).where(AIBranch.id == item.branch_id))
                    branch = branch_res.scalar_one_or_none()
                    if not branch:
                        item.status = "failed"
                        continue
                    llm = LLMClient()
                    text = await llm.generate_followup(
                        gpt_model=branch.gpt_model,
                        system_prompt="",
                        dialog_context=[],
                        followup_instruction="followup",
                    )

                if step.target_channel == "telegram_user":
                    await bot.send_message(chat_id=item.user_id, text=text)
                elif step.target_channel == "telegram_manager" and settings.ADMIN_CHAT_ID:
                    await bot.send_message(chat_id=settings.ADMIN_CHAT_ID, text=text)
                elif step.target_channel == "avito_dialog":
                    logger.info("avito_dialog target selected for followup id=%s", item.id)

                session.add(
                    AIDialogMessage(
                        user_id=item.user_id,
                        branch_id=item.branch_id,
                        dialog_id=item.dialog_id,
                        role="assistant",
                        content=text,
                        created_at=datetime.utcnow(),
                    )
                )
                item.status = "sent"
            except Exception:
                logger.exception("process_followups failed for id=%s", item.id)
                item.status = "failed"


async def stop_scheduler() -> None:
    global scheduler
    if scheduler and scheduler.running:
        scheduler.shutdown(wait=False)
        scheduler = None
        logger.info("Scheduler stopped.")
