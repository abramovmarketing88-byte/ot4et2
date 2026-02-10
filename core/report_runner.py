"""
Запуск отчётов: fetch_all_metrics и отправка в chat_id.
"""
import json
import logging
from typing import Any

from aiogram import Bot
from aiogram.enums import ParseMode
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from core.avito.auth import AvitoAuth
from core.avito.client import AvitoClient
from core.config import settings
from core.database.models import AvitoProfile, ReportTask
from core.database.session import get_session
from core.timezone import (
    date_range_formatted,
    moscow_date_range_yesterday,
    moscow_time_str,
    moscow_yesterday_formatted,
)
from utils.analytics import AnalyticsMetrics
from utils.formatter import escape_md, format_report_md2, format_error_md2

logger = logging.getLogger(__name__)

# Бот передаётся при старте планировщика (не через args джоба — Bot не сериализуется)
_current_bot: Bot | None = None


def set_report_bot(bot: Bot) -> None:
    """Установить экземпляр бота для отправки отчётов из планировщика."""
    global _current_bot
    _current_bot = bot


def _parse_balance_value(value: Any) -> float | None:
    """Баланс из API: может быть в рублях или копейках (число > 1000 скорее копейки)."""
    if value is None:
        return None
    try:
        v = float(value)
        if v > 100_000:
            return round(v / 100.0, 2)
        return round(v, 2)
    except (TypeError, ValueError):
        return None


def _parse_profile_stats_response(data: dict) -> AnalyticsMetrics:
    """Парсинг ответа stats/v2 (grouping totals). Все расходы из API в копейках → рубли."""
    metrics = AnalyticsMetrics()
    result = data.get("result", {})
    groupings = result.get("groupings", [])
    if isinstance(groupings, dict):
        groupings = [groupings]
    for g in groupings:
        totals = g.get("totals") or g
        if not isinstance(totals, dict):
            continue
        metrics.views += totals.get("views", 0)
        metrics.uniq_views += totals.get("views", 0)
        metrics.uniq_contacts += totals.get("contacts", 0)
        metrics.uniq_favorites += totals.get("favorites", 0)
        # Расходы за период (в копейках)
        metrics.total_spending += (totals.get("allSpending", 0) or totals.get("spending", 0)) / 100.0
        metrics.presence_spending += (totals.get("presenceSpending") or 0) / 100.0
        metrics.promo_spending += (totals.get("promoSpending") or 0) / 100.0
        metrics.rest_spending += (totals.get("restSpending") or 0) / 100.0
        metrics.active_items += totals.get("activeItems", 0)
    return metrics


async def fetch_all_metrics(
    access_token: str,
    user_id: int,
    date_from: str,
    date_to: str,
) -> AnalyticsMetrics:
    """
    Загрузить все метрики из Avito API за период.

    :param access_token: Bearer-токен Avito
    :param user_id: Avito user_id (из /core/v1/accounts/self)
    :param date_from: YYYY-MM-DD
    :param date_to: YYYY-MM-DD
    :return: AnalyticsMetrics (views, uniq_contacts, total_spending, CR, CPL)
    """
    client = AvitoClient(access_token)
    # Запрашиваем максимум метрик по статистике (расходы в копейках)
    data = await client.get_profile_stats(
        user_id=user_id,
        date_from=date_from,
        date_to=date_to,
        metrics=[
            "views", "contacts", "favorites",
            "allSpending", "spending", "presenceSpending", "promoSpending", "restSpending",
            "activeItems",
        ],
        grouping="totals",
    )
    metrics = _parse_profile_stats_response(data)
    # Баланс кошелька и аванс (если API доступен)
    try:
        balance_data = await client.get_balance(user_id)
        if balance_data:
            # Ожидаем real (кошелёк) и advance (аванс) в рублях или копейках
            metrics.wallet_balance = _parse_balance_value(balance_data.get("real") or balance_data.get("balance"))
            metrics.advance_balance = _parse_balance_value(balance_data.get("advance"))
    except Exception:
        pass
    if metrics.views == 0 and metrics.uniq_contacts == 0:
        items_resp = await client.get_items(status="active", per_page=100)
        resources = items_resp.get("resources", [])
        item_ids = [r.get("id") for r in resources if r.get("id")]
        if item_ids:
            stats_resp = await client.get_items_stats(
                user_id=user_id,
                item_ids=item_ids[:200],
                date_from=date_from,
                date_to=date_to,
                fields=["uniqViews", "uniqContacts", "uniqFavorites"],
            )
            items_data = stats_resp.get("result", {}).get("items", [])
            for item in items_data:
                for st in item.get("stats", []):
                    metrics.views += st.get("uniqViews", 0)
                    metrics.uniq_contacts += st.get("uniqContacts", 0)
                    metrics.uniq_favorites += st.get("uniqFavorites", 0)
    return metrics


async def _notify_admin(bot: Bot, text: str) -> None:
    """Отправить уведомление админу при ошибке токена и т.д."""
    admin_chat_id = getattr(settings, "ADMIN_CHAT_ID", None)
    if not admin_chat_id:
        return
    try:
        await bot.send_message(admin_chat_id, text)
    except Exception as e:
        logger.warning("Failed to notify admin: %s", e)


async def run_report(
    bot: Bot,
    task: ReportTask,
    profile: AvitoProfile,
    start_date: str | None = None,
    end_date: str | None = None,
) -> None:
    """
    Получить токен, вызвать fetch_all_metrics за период, отправить отчёт в task.chat_id.

    Если заданы start_date и end_date (YYYY-MM-DD), формируется отчёт строго за этот
    период (Historical Report). Иначе — за вчера по Москве.
    При ошибке обновления токена — уведомить админа.
    """
    chat_id = task.chat_id
    if not chat_id:
        logger.warning("ReportTask id=%s has no chat_id, skip", task.id)
        return

    try:
        auth = AvitoAuth(profile)
        token = await auth.ensure_token()
    except Exception as e:
        logger.exception("AvitoAuth failed for profile id=%s", profile.id)
        await _notify_admin(
            bot,
            f"⚠️ <b>Ошибка обновления токена Avito</b>\n\n"
            f"Профиль: {profile.profile_name} (id={profile.id})\n"
            f"Ошибка: <code>{e!s}</code>",
        )
        try:
            await bot.send_message(
                chat_id,
                format_error_md2(profile.profile_name, str(e)),
                parse_mode=ParseMode.MARKDOWN_V2,
            )
        except Exception:
            pass
        return

    user_id = profile.user_id
    if not user_id:
        try:
            await bot.send_message(
                chat_id,
                format_error_md2(
                    profile.profile_name,
                    "Avito user_id не получен. Выполните настройку профиля.",
                ),
                parse_mode=ParseMode.MARKDOWN_V2,
            )
        except Exception:
            pass
        return

    if start_date and end_date:
        date_from, date_to = start_date, end_date
        period_str = date_range_formatted(date_from, date_to)
    else:
        date_from, date_to = moscow_date_range_yesterday()
        period_str = moscow_yesterday_formatted()

    try:
        metrics = await fetch_all_metrics(token, user_id, date_from, date_to)
    except Exception as e:
        logger.exception("Avito API failed for profile id=%s", profile.id)
        try:
            await bot.send_message(
                chat_id,
                format_error_md2(profile.profile_name, str(e)),
                parse_mode=ParseMode.MARKDOWN_V2,
            )
        except Exception:
            pass
        return

    selected_metrics = None
    if task.report_metrics:
        try:
            selected_metrics = json.loads(task.report_metrics)
        except (TypeError, json.JSONDecodeError):
            pass
    text = format_report_md2(profile.profile_name, period_str, metrics, selected_metrics=selected_metrics)
    try:
        await bot.send_message(
            chat_id,
            text,
            parse_mode=ParseMode.MARKDOWN_V2,
        )
        logger.info("Report sent for task id=%s to chat_id=%s", task.id, chat_id)
    except Exception as e:
        logger.exception("Failed to send report to chat_id=%s", chat_id)
        try:
            await bot.send_message(chat_id, f"Ошибка отправки отчёта: {e!s}")
        except Exception:
            pass


async def run_report_to_chat(
    bot: Bot,
    profile: AvitoProfile,
    chat_id: int,
    selected_metrics: list[str] | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
) -> None:
    """
    Отправить отчёт в указанный чат (по запросу «Получить отчёт сейчас» или исторический).

    Если заданы start_date и end_date (YYYY-MM-DD), данные запрашиваются строго за этот
    период (Historical Report). Иначе — за вчера по Москве.
    """
    try:
        auth = AvitoAuth(profile)
        token = await auth.ensure_token()
    except Exception as e:
        logger.exception("AvitoAuth failed for profile id=%s", profile.id)
        await _notify_admin(
            bot,
            f"⚠️ <b>Ошибка обновления токена Avito</b>\n\n"
            f"Профиль: {profile.profile_name} (id={profile.id})\n"
            f"Ошибка: <code>{e!s}</code>",
        )
        try:
            await bot.send_message(
                chat_id,
                format_error_md2(profile.profile_name, str(e)),
                parse_mode=ParseMode.MARKDOWN_V2,
            )
        except Exception:
            pass
        return

    user_id = profile.user_id
    if not user_id:
        try:
            await bot.send_message(
                chat_id,
                format_error_md2(
                    profile.profile_name,
                    "Avito user_id не получен. Выполните настройку профиля.",
                ),
                parse_mode=ParseMode.MARKDOWN_V2,
            )
        except Exception:
            pass
        return

    if start_date and end_date:
        date_from, date_to = start_date, end_date
        period_str = date_range_formatted(date_from, date_to)
    else:
        date_from, date_to = moscow_date_range_yesterday()
        period_str = moscow_yesterday_formatted()

    try:
        metrics = await fetch_all_metrics(token, user_id, date_from, date_to)
    except Exception as e:
        logger.exception("Avito API failed for profile id=%s", profile.id)
        try:
            await bot.send_message(
                chat_id,
                format_error_md2(profile.profile_name, str(e)),
                parse_mode=ParseMode.MARKDOWN_V2,
            )
        except Exception:
            pass
        return

    text = format_report_md2(
        profile.profile_name, period_str, metrics, selected_metrics=selected_metrics
    )
    try:
        await bot.send_message(
            chat_id,
            text,
            parse_mode=ParseMode.MARKDOWN_V2,
        )
        logger.info("Report sent on demand to chat_id=%s for profile id=%s", chat_id, profile.id)
    except Exception as e:
        logger.exception("Failed to send report to chat_id=%s", chat_id)
        try:
            await bot.send_message(chat_id, f"Ошибка отправки отчёта: {e!s}")
        except Exception:
            pass


def _sum_optional(*values: float | None) -> float | None:
    """Суммировать optional-значения (None игнорируется)."""
    non_null = [v for v in values if v is not None]
    if not non_null:
        return None
    return round(sum(non_null), 2)


def _aggregate_metrics(metrics_list: list[AnalyticsMetrics]) -> AnalyticsMetrics:
    """Сложить метрики нескольких аккаунтов в одну сводку."""
    total = AnalyticsMetrics()
    for metrics in metrics_list:
        total.views += metrics.views
        total.uniq_views += metrics.uniq_views
        total.contacts += metrics.contacts
        total.uniq_contacts += metrics.uniq_contacts
        total.favorites += metrics.favorites
        total.uniq_favorites += metrics.uniq_favorites
        total.total_spending += metrics.total_spending
        total.presence_spending += metrics.presence_spending
        total.promo_spending += metrics.promo_spending
        total.rest_spending += metrics.rest_spending
        total.active_items += metrics.active_items
        total.wallet_balance = _sum_optional(total.wallet_balance, metrics.wallet_balance)
        total.advance_balance = _sum_optional(total.advance_balance, metrics.advance_balance)
    return total


async def run_combined_report_to_chat(
    bot: Bot,
    profiles: list[AvitoProfile],
    chat_id: int,
    selected_metrics: list[str] | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
) -> None:
    """Сформировать один общий отчёт по нескольким Avito-профилям."""
    if not profiles:
        return

    if start_date and end_date:
        date_from, date_to = start_date, end_date
        period_str = date_range_formatted(date_from, date_to)
    else:
        date_from, date_to = moscow_date_range_yesterday()
        period_str = moscow_yesterday_formatted()

    collected: list[AnalyticsMetrics] = []
    failed_profiles: list[str] = []
    included_names: list[str] = []

    for profile in profiles:
        try:
            auth = AvitoAuth(profile)
            token = await auth.ensure_token()
            if not profile.user_id:
                raise ValueError("Avito user_id не получен. Выполните настройку профиля.")
            metrics = await fetch_all_metrics(token, profile.user_id, date_from, date_to)
            collected.append(metrics)
            included_names.append(profile.profile_name)
        except Exception as e:
            logger.exception("Failed to collect profile metrics for profile id=%s", profile.id)
            failed_profiles.append(f"{profile.profile_name}: {e!s}")

    if not collected:
        if failed_profiles:
            await bot.send_message(
                chat_id,
                "⚠️ Не удалось сформировать сводный отчёт по выбранным аккаунтам:\n\n"
                + "\n".join(failed_profiles),
            )
        return

    merged = _aggregate_metrics(collected)
    report_name = f"Сводный отчёт ({len(included_names)} аккаунтов)"
    text = format_report_md2(report_name, period_str, merged, selected_metrics=selected_metrics)
    if failed_profiles:
        failed_lines = "\n".join(f"• {escape_md(item)}" for item in failed_profiles)
        warning = "\n\n⚠️ *Не вошли в сводку:*\n" + failed_lines
        text += warning

    try:
        await bot.send_message(chat_id, text, parse_mode=ParseMode.MARKDOWN_V2)
        logger.info("Combined report sent to chat_id=%s for %s profile(s)", chat_id, len(included_names))
    except Exception as e:
        logger.exception("Failed to send combined report to chat_id=%s", chat_id)
        try:
            await bot.send_message(chat_id, f"Ошибка отправки сводного отчёта: {e!s}")
        except Exception:
            pass


async def check_report_tasks() -> None:
    """
    Проверить ReportTask: если текущее время (Москва) совпадает с report_time,
    вызвать fetch_all_metrics и отправить отчёт в chat_id каждой задачи.
    Бот берётся из _current_bot (устанавливается при start_scheduler).
    """
    bot = _current_bot
    if not bot:
        logger.warning("check_report_tasks: bot not set, skip")
        return
    now_str = moscow_time_str()
    async with get_session() as session:
        result = await session.execute(
            select(ReportTask)
            .where(ReportTask.is_active == True)
            .where(ReportTask.report_time == now_str)
            .where(ReportTask.chat_id != 0)
            .options(selectinload(ReportTask.profile))
        )
        tasks = list(result.scalars().unique().all())

    for task in tasks:
        if task.profile is None:
            continue
        try:
            await run_report(bot, task, task.profile)
        except Exception as e:
            logger.exception("run_report failed for task id=%s: %s", task.id, e)
