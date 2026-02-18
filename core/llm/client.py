"""LLM client interface for AI seller mode and followups.

This module hides the concrete provider and model names behind:
- settings.LLM_API_KEY
- LLM_MODEL_MAP (alias -> provider model)

Handlers should call the high-level methods:
- generate_reply(branch, messages)
- generate_followup(branch, prompt_template, context_data)
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Sequence

from core.config import LLM_MODEL_MAP, settings
from core.database.models import AIBranch, PromptTemplate

logger = logging.getLogger(__name__)


class LLMClient:
    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = api_key or settings.LLM_API_KEY

    def resolve_model(self, gpt_model_alias: str) -> str:
        """Map logical alias (gpt-mini/gpt-mid/...) to real provider model."""
        model = LLM_MODEL_MAP.get(gpt_model_alias, LLM_MODEL_MAP["gpt-mini"])
        return model

    async def _stub_call(self, model: str, messages: Sequence[dict[str, Any]]) -> str:
        """Fallback stub instead of a real provider call.

        Keeps behavior predictable in environments without an actual LLM provider.
        """
        await asyncio.sleep(0)
        last_user = ""
        for m in reversed(messages):
            if m.get("role") == "user":
                last_user = str(m.get("content", ""))
                break
        return (
            f"[{model}] {last_user}\n\n"
            "(stub LLM response — подключите реальный провайдер через LLM_API_KEY)"
        )

    async def generate_reply(
        self,
        branch: AIBranch,
        messages: Sequence[dict[str, Any]],
    ) -> str:
        """Generate chat reply for AI seller dialog.

        - `branch` supplies the logical gpt_model alias.
        - `messages` is a full history: list of {'role','content'} including system/user/assistant.
        """
        model = self.resolve_model(branch.gpt_model)
        try:
            # Here you could call a real provider (OpenAI, etc.) using `self.api_key`.
            # For now we keep a stub implementation.
            return await self._stub_call(model, messages)
        except Exception as exc:  # pragma: no cover - defensive
            logger.exception("generate_reply failed for branch_id=%s: %s", getattr(branch, "id", None), exc)
            return "⚠️ Не удалось получить ответ от LLM. Попробуйте ещё раз позже."

    async def generate_followup(
        self,
        branch: AIBranch,
        prompt_template: PromptTemplate | None,
        context_data: dict[str, Any],
    ) -> str:
        """Generate a follow-up message.

        - `branch` supplies the model alias and ownership.
        - `prompt_template` can contain system/instruction text (optional).
        - `context_data` is an arbitrary dict with dialog / state info.
        """
        model = self.resolve_model(branch.gpt_model)
        system = prompt_template.content if prompt_template else ""
        # Simplified context → two messages: system + user instruction with context snapshot.
        messages: list[dict[str, Any]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append(
            {
                "role": "user",
                "content": f"Сгенерируй follow-up сообщение с учётом контекста: {context_data!r}",
            }
        )
        try:
            return await self._stub_call(model, messages)
        except Exception as exc:  # pragma: no cover - defensive
            logger.exception(
                "generate_followup failed for branch_id=%s prompt_id=%s: %s",
                getattr(branch, "id", None),
                getattr(prompt_template, "id", None) if prompt_template else None,
                exc,
            )
            return "⚠️ Не удалось сгенерировать follow-up сообщение."
