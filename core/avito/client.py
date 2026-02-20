"""
Avito API клиент: Items, Stats, Calls.

Документация: https://developers.avito.ru/api-catalog
"""
from typing import Any

import httpx

AVITO_API_BASE = "https://api.avito.ru"


class AvitoClient:
    """Клиент для вызовов Avito API."""

    def __init__(self, access_token: str) -> None:
        self._token = access_token
        self._headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }

    async def _request(
        self,
        method: str,
        path: str,
        params: dict | None = None,
        json: dict | None = None,
    ) -> dict[str, Any]:
        url = f"{AVITO_API_BASE}{path}"
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.request(
                method,
                url,
                headers=self._headers,
                params=params,
                json=json,
            )
            resp.raise_for_status()
            return resp.json() if resp.content else {}

    # ═══════════════════════════════════════════════════════════════════════════
    # Items (Объявления)
    # ═══════════════════════════════════════════════════════════════════════════

    async def get_items(
        self,
        status: str = "active",
        per_page: int = 25,
        page: int = 1,
    ) -> dict[str, Any]:
        """
        GET /core/v1/items
        Список объявлений пользователя.

        :param status: active | removed | old | blocked | rejected (можно через запятую)
        :param per_page: 1..100
        :param page: >= 1
        """
        return await self._request(
            "GET",
            "/core/v1/items",
            params={"status": status, "per_page": per_page, "page": page},
        )

    async def get_active_item_ids(self, max_items: int = 500) -> list[int]:
        """
        Список ID активных объявлений (пагинация).
        Для применения лимитов CPX Promo по профилю.
        """
        ids: list[int] = []
        page = 1
        per_page = 100
        while len(ids) < max_items:
            data = await self.get_items(status="active", per_page=per_page, page=page)
            resources = data.get("resources", [])
            for r in resources:
                if r.get("id") is not None:
                    ids.append(int(r["id"]))
            if len(resources) < per_page:
                break
            page += 1
        return ids[:max_items]

    async def get_item_info(self, user_id: int, item_id: int) -> dict[str, Any]:
        """
        GET /core/v1/accounts/{user_id}/items/{item_id}/
        Информация по объявлению (статус, VAS, даты).
        """
        return await self._request(
            "GET",
            f"/core/v1/accounts/{user_id}/items/{item_id}/",
        )

    # ═══════════════════════════════════════════════════════════════════════════
    # Stats (Статистика)
    # ═══════════════════════════════════════════════════════════════════════════

    async def get_items_stats(
        self,
        user_id: int,
        item_ids: list[int],
        date_from: str,
        date_to: str,
        fields: list[str] | None = None,
        period_grouping: str = "day",
    ) -> dict[str, Any]:
        """
        POST /stats/v1/accounts/{user_id}/items
        Статистика по списку объявлений (до 200 шт, глубина 270 дней).

        :param item_ids: список ID объявлений
        :param date_from: YYYY-MM-DD
        :param date_to: YYYY-MM-DD
        :param fields: views, uniqViews, contacts, uniqContacts, favorites, uniqFavorites
        :param period_grouping: day | week | month
        """
        if fields is None:
            fields = ["uniqViews", "uniqContacts", "uniqFavorites"]
        return await self._request(
            "POST",
            f"/stats/v1/accounts/{user_id}/items",
            json={
                "dateFrom": date_from,
                "dateTo": date_to,
                "fields": fields,
                "itemIds": item_ids,
                "periodGrouping": period_grouping,
            },
        )

    async def get_profile_stats(
        self,
        user_id: int,
        date_from: str,
        date_to: str,
        metrics: list[str],
        grouping: str = "day",
        limit: int = 1000,
        offset: int = 0,
    ) -> dict[str, Any]:
        """
        POST /stats/v2/accounts/{user_id}/items
        Статистика по профилю (расширенная, глубина 270 дней).

        :param metrics: views, contacts, favorites, spending, presenceSpending, promoSpending и др.
        :param grouping: totals | item | day | week | month
        """
        return await self._request(
            "POST",
            f"/stats/v2/accounts/{user_id}/items",
            json={
                "dateFrom": date_from,
                "dateTo": date_to,
                "metrics": metrics,
                "grouping": grouping,
                "limit": limit,
                "offset": offset,
            },
        )

    # ═══════════════════════════════════════════════════════════════════════════
    # Calls (Звонки)
    # ═══════════════════════════════════════════════════════════════════════════

    async def get_calls_stats(
        self,
        user_id: int,
        date_from: str,
        date_to: str,
        item_ids: list[int] | None = None,
    ) -> dict[str, Any]:
        """
        POST /core/v1/accounts/{user_id}/calls/stats/
        Агрегированная статистика звонков.

        :param date_from: YYYY-MM-DD
        :param date_to: YYYY-MM-DD
        :param item_ids: опционально — фильтр по объявлениям
        """
        body: dict[str, Any] = {"dateFrom": date_from, "dateTo": date_to}
        if item_ids:
            body["itemIds"] = item_ids
        return await self._request(
            "POST",
            f"/core/v1/accounts/{user_id}/calls/stats/",
            json=body,
        )

    # ═══════════════════════════════════════════════════════════════════════════
    # VAS (Услуги продвижения)
    # ═══════════════════════════════════════════════════════════════════════════

    async def get_vas_prices(
        self,
        user_id: int,
        item_ids: list[int],
    ) -> dict[str, Any]:
        """
        POST /core/v1/accounts/{userId}/vas/prices
        Стоимость услуг продвижения и доступных значков.
        """
        return await self._request(
            "POST",
            f"/core/v1/accounts/{user_id}/vas/prices",
            json={"itemIds": item_ids},
        )

    async def update_item_price(self, item_id: int, price: int) -> dict[str, Any]:
        """
        POST /core/v1/items/{item_id}/update_price
        Обновление цены объявления.
        """
        return await self._request(
            "POST",
            f"/core/v1/items/{item_id}/update_price",
            json={"price": price},
        )

    # ═══════════════════════════════════════════════════════════════════════════
    # Messenger (чаты и сообщения) — scope messenger
    # Документация: https://developers.avito.ru/api-catalog/messenger/documentation
    # ═══════════════════════════════════════════════════════════════════════════

    async def get_conversations(
        self,
        user_id: int,
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        """
        GET /messenger/v1/accounts/{user_id}/chats/
        Список активных чатов (диалогов).

        :param user_id: Avito user_id (из /core/v1/accounts/self)
        :param limit: макс. количество чатов (1..100)
        :param offset: смещение для пагинации
        :return: {"chats": [...], "total": N} — каждый чат: id, context, users, last_message, created, updated
        """
        return await self._request(
            "GET",
            f"/messenger/v1/accounts/{user_id}/chats/",
            params={"limit": limit, "offset": offset},
        )

    async def get_messages(
        self,
        user_id: int,
        chat_id: str | int,
        limit: int = 100,
        offset: int = 0,
    ) -> dict[str, Any]:
        """
        GET /messenger/v1/accounts/{user_id}/chats/{chat_id}/messages/
        История сообщений в чате.

        :param user_id: Avito user_id
        :param chat_id: ID чата (из get_conversations)
        :param limit: макс. сообщений (1..100)
        :param offset: смещение для пагинации
        :return: {"messages": [...]} — каждое: id, author_id, created, content.text, type, direction
        """
        return await self._request(
            "GET",
            f"/messenger/v1/accounts/{user_id}/chats/{chat_id}/messages/",
            params={"limit": limit, "offset": offset},
        )

    async def send_message_text(
        self,
        user_id: int,
        chat_id: str | int,
        text: str,
    ) -> dict[str, Any]:
        """
        POST /messenger/v1/accounts/{user_id}/chats/{chat_id}/messages
        Отправка текстового сообщения в чат.
        """
        payload = {"type": "text", "message": {"text": text}}
        return await self._request(
            "POST",
            f"/messenger/v1/accounts/{user_id}/chats/{chat_id}/messages",
            json=payload,
        )

    async def mark_chat_read(
        self,
        user_id: int,
        chat_id: str | int,
    ) -> dict[str, Any]:
        """
        POST /messenger/v1/accounts/{user_id}/chats/{chat_id}/read
        Отметить чат прочитанным.
        """
        return await self._request(
            "POST",
            f"/messenger/v1/accounts/{user_id}/chats/{chat_id}/read",
        )

    # ═══════════════════════════════════════════════════════════════════════════
    # Баланс (кошелёк, аванс) — scope user_balance:read
    # ═══════════════════════════════════════════════════════════════════════════

    async def get_balance(self, user_id: int) -> dict[str, Any]:
        """
        GET /core/v1/accounts/{user_id}/balance/
        Баланс: кошелёк (real), аванс (advance) в рублях.
        При 404 или отсутствии scope возвращает {}.
        """
        try:
            return await self._request(
                "GET",
                f"/core/v1/accounts/{user_id}/balance/",
            )
        except Exception:
            return {}
