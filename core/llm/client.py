"""LLM client interface for AI seller mode."""
import asyncio
from typing import Any

from core.config import LLM_MODEL_MAP, settings


class LLMClient:
    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = api_key or settings.LLM_API_KEY

    def resolve_model(self, gpt_model: str) -> str:
        return LLM_MODEL_MAP.get(gpt_model, LLM_MODEL_MAP["gpt-mini"])

    async def generate_reply(
        self,
        gpt_model: str,
        system_prompt: str,
        dialog_context: list[dict[str, Any]],
        user_message: str,
    ) -> str:
        model_name = self.resolve_model(gpt_model)
        await asyncio.sleep(0)
        return (
            f"[{model_name}] "
            f"{user_message}\n\n"
            f"(stub: подключите реальный провайдер через LLM_API_KEY)"
        )

    async def generate_followup(
        self,
        gpt_model: str,
        system_prompt: str,
        dialog_context: list[dict[str, Any]],
        followup_instruction: str,
    ) -> str:
        model_name = self.resolve_model(gpt_model)
        await asyncio.sleep(0)
        return (
            f"[{model_name}] "
            f"{followup_instruction}\n\n"
            f"(stub: подключите реальный провайдер через LLM_API_KEY)"
        )
