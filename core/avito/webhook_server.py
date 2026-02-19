"""
Avito Messenger webhook server (aiohttp).

Минимальная реализация:
- принимает webhook от Avito
- отвечает 200 OK как можно быстрее
- обрабатывает сообщение асинхронно: сохраняет в БД, генерирует ответ, отправляет его в чат
"""
from __future__ import annotations

import asyncio
import os
import logging
from datetime import datetime
from typing import Any

from aiohttp import web
from sqlalchemy import select

from core.avito.auth import AvitoAuth
from core.avito.client import AvitoClient
from core.config import settings
from core.database.models import AIDialogMessage, AISettings, AvitoProfile
from core.database.session import get_session
from core.llm.client import LLMClient

logger = logging.getLogger(__name__)


def _extract_payload(request_json: dict[str, Any]) -> dict[str, Any]:
    """
    Универсальный разбор payload (Avito webhook может быть v2/v3).
    Возвращает плоские поля: user_id, chat_id, text, msg_type, direction, flow_id.
    """
    data = request_json.get("data") or request_json.get("payload") or request_json
    message = data.get("message") or data.get("last_message") or data

    user_id = (
        data.get("user_id")
        or data.get("account_id")
        or data.get("seller_id")
        or message.get("user_id")
        or message.get("account_id")
    )
    chat_id = data.get("chat_id") or message.get("chat_id") or data.get("id")
    msg_type = message.get("type") or message.get("content", {}).get("type")
    direction = message.get("direction")  # in/out
    flow_id = message.get("flow_id")

    content = message.get("content") or {}
    text = message.get("text") or content.get("text")

    return {
        "user_id": user_id,
        "chat_id": chat_id,
        "text": text,
        "msg_type": msg_type,
        "direction": direction,
        "flow_id": flow_id,
        "raw": request_json,
    }


async def _process_message(payload: dict[str, Any]) -> None:
    """Обработать входящее сообщение Avito и отправить AI-ответ."""
    user_id = payload.get("user_id")
    chat_id = payload.get("chat_id")
    text = (payload.get("text") or "").strip()
    msg_type = payload.get("msg_type")
    direction = payload.get("direction")
    flow_id = payload.get("flow_id")

    if not user_id or not chat_id or not text:
        logger.info("Webhook: пропуск пустого/неполного сообщения: %s", payload)
        return
    if direction == "out":
        return
    if msg_type == "system" or flow_id:
        return

    async with get_session() as session:
        r = await session.execute(
            select(AvitoProfile).where(AvitoProfile.user_id == int(user_id))
        )
        profile = r.scalar_one_or_none()
        if not profile:
            logger.warning("Webhook: профиль не найден для user_id=%s", user_id)
            return
        ai = await session.get(AISettings, profile.id)
        if not ai or not ai.is_enabled:
            logger.info("Webhook: AI отключён для profile_id=%s", profile.id)
            return

        # Сохраняем входящее сообщение
        session.add(
            AIDialogMessage(
                user_id=profile.owner_id,
                profile_id=profile.id,
                dialog_id=str(chat_id),
                role="user",
                content=text,
            )
        )

        # Контекст для LLM (последние N)
        limit = ai.context_value or 20
        hist_result = await session.execute(
            select(AIDialogMessage)
            .where(
                AIDialogMessage.profile_id == profile.id,
                AIDialogMessage.dialog_id == str(chat_id),
            )
            .order_by(AIDialogMessage.created_at.desc())
            .limit(limit)
        )
        history = list(reversed(hist_result.scalars().all()))
        messages: list[dict[str, Any]] = []
        if ai.system_prompt:
            messages.append({"role": "system", "content": ai.system_prompt})
        for m in history:
            messages.append({"role": m.role, "content": m.content})

        llm = LLMClient()
        reply = await llm.generate_reply(ai, messages)

        # Отправляем ответ в Avito
        try:
            token = await AvitoAuth(profile).ensure_token()
            client = AvitoClient(token)
            await client.send_message_text(int(user_id), chat_id, reply)
            await client.mark_chat_read(int(user_id), chat_id)
        except Exception as exc:
            logger.exception("Webhook: failed to send reply (profile_id=%s): %s", profile.id, exc)
            return

        # Сохраняем ответ
        session.add(
            AIDialogMessage(
                user_id=profile.owner_id,
                profile_id=profile.id,
                dialog_id=str(chat_id),
                role="assistant",
                content=reply,
            )
        )
        logger.info(
            "Webhook: reply sent (profile_id=%s, chat_id=%s, ts=%s)",
            profile.id,
            chat_id,
            datetime.utcnow().isoformat(),
        )


async def handle_avito_webhook(request: web.Request) -> web.Response:
    """HTTP handler for Avito webhook (must return 200 quickly)."""
    try:
        payload = await request.json()
    except Exception:
        return web.json_response({"ok": False, "error": "invalid_json"}, status=400)

    # Опциональный shared secret
    if settings.AVITO_WEBHOOK_SECRET:
        secret = request.headers.get("X-Avito-Secret") or request.headers.get("X-Webhook-Secret")
        if secret != settings.AVITO_WEBHOOK_SECRET:
            logger.warning("Webhook: invalid secret")
            return web.json_response({"ok": False, "error": "invalid_secret"}, status=403)

    data = _extract_payload(payload)
    asyncio.create_task(_process_message(data))
    return web.json_response({"ok": True})


async def start_webhook_server() -> web.AppRunner | None:
    """Запуск aiohttp сервера для Avito webhook."""
    if not settings.AVITO_WEBHOOK_ENABLED:
        return None
    port = settings.AVITO_WEBHOOK_PORT
    env_port = os.getenv("PORT")
    if env_port and (port == 8000 or port is None):
        try:
            port = int(env_port)
        except ValueError:
            pass
    app = web.Application()
    app.router.add_post(settings.AVITO_WEBHOOK_PATH, handle_avito_webhook)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, settings.AVITO_WEBHOOK_HOST, port)
    await site.start()
    logger.info(
        "Avito webhook server started on http://%s:%s%s",
        settings.AVITO_WEBHOOK_HOST,
        port,
        settings.AVITO_WEBHOOK_PATH,
    )
    return runner


async def stop_webhook_server(runner: web.AppRunner | None) -> None:
    if runner is None:
        return
    await runner.cleanup()
    logger.info("Avito webhook server stopped.")
