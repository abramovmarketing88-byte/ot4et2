"""
Применение суточных лимитов CPX Promo по профилю на указанную дату.

Используется планировщиком (23:59) и кнопками «Применить сейчас» / «Применить на сегодня».
Часовой пояс: Europe/Moscow (конфиг в core.scheduler).
"""
import logging
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from core.avito.auth import AvitoAuth
from core.avito.client import AvitoClient
from core.avito import cpxpromo
from core.database.models import AvitoProfile, ProfileDailyLimits
from core.database.session import get_session

logger = logging.getLogger(__name__)

PENNY_ATTRS = [
    "mon_penny", "tue_penny", "wed_penny", "thu_penny",
    "fri_penny", "sat_penny", "sun_penny",
]


def _penny_for_weekday(limits: ProfileDailyLimits, target_date: date) -> int:
    """Лимит в копейках на день недели (Пн=0 .. Вс=6)."""
    wd = target_date.weekday()
    return getattr(limits, PENNY_ATTRS[wd], 0)


async def apply_daily_limit_for_profile(
    profile_id: int,
    target_date: date,
) -> tuple[int, int, list[str]]:
    """
    Применить лимит на target_date ко всем активным объявлениям профиля.

    :return: (успешно, ошибок, список сообщений об ошибках).
    """
    async with get_session() as session:
        r = await session.execute(
            select(AvitoProfile)
            .where(AvitoProfile.id == profile_id)
            .options(selectinload(AvitoProfile.daily_limits))
        )
        profile = r.scalar_one_or_none()
    if not profile:
        return 0, 0, ["Профиль не найден"]
    limits = profile.daily_limits
    if not limits:
        return 0, 0, ["Настройки лимитов по дням не найдены"]

    penny = _penny_for_weekday(limits, target_date)
    mode = limits.mode or "auto_budget"
    action_type_id = limits.action_type_id or 5

    auth = AvitoAuth(profile)
    try:
        token = await auth.ensure_token()
    except Exception as e:
        logger.exception("Daily limits: token for profile %s failed", profile_id)
        return 0, 0, [f"Токен недоступен: {e!s}"]

    client = AvitoClient(token)
    try:
        item_ids = await client.get_active_item_ids()
    except Exception as e:
        logger.exception("Daily limits: get_items for profile %s failed", profile_id)
        return 0, 0, [f"Не удалось получить список объявлений: {e!s}"]

    if not item_ids:
        logger.info("Daily limits: profile %s has no active items", profile_id)
        return 0, 0, []

    errors: list[str] = []
    ok_count = 0
    err_count = 0

    for item_id in item_ids:
        try:
            if mode == "manual":
                bids = await cpxpromo.get_bids(token, item_id)
                bid_penny = None
                if isinstance(bids, dict) and "result" in bids:
                    res = bids["result"]
                    if isinstance(res, list) and res:
                        bid_penny = res[0].get("bidPenny") or res[0].get("bid_penny")
                    elif isinstance(res, dict):
                        bid_penny = res.get("bidPenny") or res.get("bid_penny")
                if bid_penny is None:
                    errors.append(f"Объявление {item_id}: нет ставки (getBids). Включите AUTO или задайте ставку вручную.")
                    err_count += 1
                    continue
                await cpxpromo.set_manual_daily_limit(
                    token, item_id, limit_penny=penny, bid_penny=int(bid_penny), action_type_id=action_type_id
                )
            else:
                await cpxpromo.set_auto_daily_budget(
                    token, item_id, budget_penny=penny, action_type_id=action_type_id
                )
            ok_count += 1
        except Exception as e:
            err_count += 1
            errors.append(f"Объявление {item_id}: {e!s}")
            logger.warning("Daily limit apply item %s failed: %s", item_id, e)

    # Обновить last_applied_date идемпотентно: ставим target_date
    async with get_session() as session:
        r = await session.execute(
            select(ProfileDailyLimits).where(ProfileDailyLimits.profile_id == profile_id)
        )
        row = r.scalar_one_or_none()
        if row:
            row.last_applied_date = target_date

    return ok_count, err_count, errors
