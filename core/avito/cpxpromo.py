"""
Avito CPX Promo API: суточный бюджет/лимит по объявлениям.

- setAuto: бюджет на день (budgetType="1d", budgetPenny в копейках).
- setManual: суточный лимит (limitPenny), требуется bidPenny (из getBids или сохранённый).
Документация: Портал разработчика Авито (CPX Promo).
"""
import asyncio
import logging
from typing import Any

import httpx

from core.avito.client import AVITO_API_BASE

logger = logging.getLogger(__name__)

# Ограничение параллельных запросов к API (429 backoff)
CPX_SEMAPHORE = asyncio.Semaphore(4)
CPX_TIMEOUT = 30.0
MAX_429_RETRIES = 3
INITIAL_BACKOFF = 2.0


async def _request_with_backoff(
    method: str,
    url: str,
    headers: dict[str, str],
    *,
    json: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Выполнить запрос с повтором при 429."""
    last_err: Exception | None = None
    for attempt in range(MAX_429_RETRIES):
        try:
            async with CPX_SEMAPHORE:
                async with httpx.AsyncClient(timeout=CPX_TIMEOUT) as client:
                    resp = await client.request(
                        method,
                        url,
                        headers=headers,
                        json=json,
                    )
            if resp.status_code == 429:
                wait = INITIAL_BACKOFF * (2**attempt)
                logger.warning("CPX 429 for %s %s, retry in %.1fs", method, url, wait)
                await asyncio.sleep(wait)
                last_err = httpx.HTTPStatusError("Rate limited", request=resp.request, response=resp)
                continue
            resp.raise_for_status()
            return resp.json() if resp.content else {}
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:
                last_err = e
                wait = INITIAL_BACKOFF * (2**attempt)
                await asyncio.sleep(wait)
                continue
            raise
    if last_err:
        raise last_err
    return {}


async def get_bids(access_token: str, item_id: int) -> dict[str, Any]:
    """
    GET /cpxpromo/1/getBids/{itemId}
    Текущие ставки по объявлению (для MANUAL нужен bidPenny).
    """
    url = f"{AVITO_API_BASE}/cpxpromo/1/getBids/{item_id}"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }
    return await _request_with_backoff("GET", url, headers)


async def set_auto_daily_budget(
    access_token: str,
    item_id: int,
    budget_penny: int,
    action_type_id: int = 5,
) -> dict[str, Any]:
    """
    POST /cpxpromo/1/setAuto
    Установить суточный бюджет (AUTO). budget_penny в копейках, кратно рублю.
    """
    url = f"{AVITO_API_BASE}/cpxpromo/1/setAuto"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }
    payload = {
        "itemID": item_id,
        "actionTypeID": action_type_id,
        "budgetType": "1d",
        "budgetPenny": budget_penny,
    }
    return await _request_with_backoff("POST", url, headers, json=payload)


async def set_manual_daily_limit(
    access_token: str,
    item_id: int,
    limit_penny: int,
    bid_penny: int,
    action_type_id: int = 5,
) -> dict[str, Any]:
    """
    POST /cpxpromo/1/setManual
    Установить суточный лимит (MANUAL). bid_penny — текущая ставка (из getBids).
    """
    url = f"{AVITO_API_BASE}/cpxpromo/1/setManual"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }
    payload = {
        "itemID": item_id,
        "actionTypeID": action_type_id,
        "bidPenny": bid_penny,
        "limitPenny": limit_penny,
    }
    return await _request_with_backoff("POST", url, headers, json=payload)
