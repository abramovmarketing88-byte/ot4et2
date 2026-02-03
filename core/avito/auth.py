"""
AvitoAuth: OAuth 2.0 client_credentials с автообновлением токена.
Все timestamp в БД — UTC (core.timezone.utc_now).
"""
from datetime import timedelta

import httpx

from core.database.models import AvitoProfile
from core.database.session import get_session
from core.timezone import utc_now

AVITO_TOKEN_URL = "https://api.avito.ru/token"
AVITO_API_BASE = "https://api.avito.ru"

# Буфер перед истечением токена (обновляем заранее)
TOKEN_REFRESH_BUFFER_SECONDS = 60


class AvitoAuth:
    """
    Авторизация Avito по client_credentials.
    
    Автоматически обновляет токен при истечении.
    """

    def __init__(self, profile: AvitoProfile) -> None:
        self._profile = profile

    @property
    def profile_id(self) -> int:
        return self._profile.id

    def _is_token_expired(self) -> bool:
        """Проверка, истёк ли токен (с учётом буфера). token_expires_at в БД — UTC."""
        if not self._profile.access_token or not self._profile.token_expires_at:
            return True
        buffer = timedelta(seconds=TOKEN_REFRESH_BUFFER_SECONDS)
        return utc_now() >= (self._profile.token_expires_at - buffer)

    async def _fetch_token(self) -> dict:
        """Запрос нового access_token по client_credentials."""
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                AVITO_TOKEN_URL,
                data={
                    "grant_type": "client_credentials",
                    "client_id": self._profile.client_id,
                    "client_secret": self._profile.client_secret,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            resp.raise_for_status()
            return resp.json()

    async def _save_token(self, token_data: dict) -> None:
        """Сохранить токен в БД (token_expires_at в UTC)."""
        expires_in = token_data.get("expires_in", 3600)
        async with get_session() as session:
            profile = await session.get(AvitoProfile, self._profile.id)
            if profile:
                profile.access_token = token_data["access_token"]
                profile.token_expires_at = utc_now() + timedelta(seconds=expires_in)
                # Обновляем локальный объект
                self._profile.access_token = profile.access_token
                self._profile.token_expires_at = profile.token_expires_at

    async def ensure_token(self) -> str:
        """
        Получить актуальный access_token.
        
        Если токен истёк или отсутствует — запрашивает новый и сохраняет в БД.
        """
        if self._is_token_expired():
            token_data = await self._fetch_token()
            await self._save_token(token_data)
        return self._profile.access_token  # type: ignore

    async def get_and_save_user_id(self) -> int:
        """
        Получить user_id из Avito API и сохранить в БД.
        
        GET https://api.avito.ru/core/v1/accounts/self
        
        Возвращает числовой user_id.
        """
        token = await self.ensure_token()
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(
                f"{AVITO_API_BASE}/core/v1/accounts/self",
                headers={"Authorization": f"Bearer {token}"},
            )
            resp.raise_for_status()
            data = resp.json()

        user_id: int = data["id"]

        # Сохраняем user_id в БД
        async with get_session() as session:
            profile = await session.get(AvitoProfile, self._profile.id)
            if profile:
                profile.user_id = user_id
                self._profile.user_id = user_id

        return user_id

    async def refresh_token(self) -> str:
        """Принудительное обновление токена."""
        token_data = await self._fetch_token()
        await self._save_token(token_data)
        return self._profile.access_token  # type: ignore
