"""LLM client interface for AI seller mode and followups."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Sequence

from core.config import LLM_MODEL_MAP, settings
from core.database.models import AISettings

logger = logging.getLogger(__name__)


class LLMClient:
    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = api_key or settings.LLM_API_KEY

    def resolve_model(self, model_alias: str) -> str:
        if model_alias == "gpt-4o-mini":
            return "gpt-4o-mini"
        return LLM_MODEL_MAP.get(model_alias, "gpt-4o-mini")

    async def _stub_call(self, model: str, messages: Sequence[dict[str, Any]]) -> str:
        await asyncio.sleep(0)
        last_user = ""
        for m in reversed(messages):
            if m.get("role") == "user":
                last_user = str(m.get("content", ""))
                break
        return f"[{model}] {last_user}\n\n(stub LLM response)"

    async def generate_reply(self, ai_settings: AISettings, messages: Sequence[dict[str, Any]]) -> str:
        model = self.resolve_model(ai_settings.model_alias)
        try:
            return await self._stub_call(model, messages)
        except Exception as exc:  # pragma: no cover
            logger.exception("generate_reply failed for profile_id=%s: %s", ai_settings.profile_id, exc)
            return "⚠️ Не удалось получить ответ от LLM."

    async def generate_followup(self, ai_settings: AISettings, content_text: str, context_data: dict[str, Any]) -> str:
        model = self.resolve_model(ai_settings.model_alias)
        messages = [
            {"role": "system", "content": content_text or "Сгенерируй follow-up"},
            {"role": "user", "content": f"Контекст: {context_data!r}"},
        ]
        try:
            return await self._stub_call(model, messages)
        except Exception as exc:  # pragma: no cover
            logger.exception("generate_followup failed for profile_id=%s: %s", ai_settings.profile_id, exc)
            return "⚠️ Не удалось сгенерировать follow-up сообщение."
