"""
Проверка импортов и ключевых модулей без BOT_TOKEN/DATABASE_URL.
Запуск: python scripts/check_imports.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# Корень проекта в PYTHONPATH
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Без реальных env импорт core.config упадёт — подменяем минимально
os.environ.setdefault("BOT_TOKEN", "test-token-for-import-check")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")

def main() -> int:
    errors: list[str] = []

    # 1. Модели (без подключения к БД)
    try:
        from core.database.models import (
            User,
            AvitoProfile,
            AISettings,
            TelegramTarget,
            TelegramBusinessConnection,
        )
        assert TelegramTarget.__tablename__ == "telegram_targets"
        assert TelegramBusinessConnection.__tablename__ == "telegram_business_connections"
    except Exception as e:
        errors.append(f"core.database.models: {e}")

    # 2. LLM client (stub при пустом ключе)
    try:
        from core.llm.client import LLMClient
        client = LLMClient(api_key="")
        assert client.api_key == ""
        # resolve_model
        assert client.resolve_model("gpt-4o-mini") == "gpt-4o-mini"
    except Exception as e:
        errors.append(f"core.llm.client: {e}")

    # 3. Клавиатуры (без БД)
    try:
        from bot.keyboards import (
            start_main_menu_kb,
            integrations_menu_kb,
            telegram_integration_kb,
            ai_set_prompt_kb,
        )
        kb = start_main_menu_kb()
        assert kb is not None
        kb2 = integrations_menu_kb()
        assert kb2 is not None
        kb3 = telegram_integration_kb()
        assert kb3 is not None
        kb4 = ai_set_prompt_kb(1)
        assert kb4 is not None
    except Exception as e:
        errors.append(f"bot.keyboards: {e}")

    # 4. Роутеры и обработчик business_connection (импорт)
    try:
        from bot.handlers.integrations import router as int_router
        from bot.handlers.telegram_integration import router as tg_router, on_business_connection_update
        assert int_router.name == "integrations"
        assert callable(on_business_connection_update)
    except Exception as e:
        errors.append(f"bot.handlers (integrations/telegram): {e}")

    # 5. ai_mode router
    try:
        from bot.handlers.ai_mode import router as ai_router
        assert ai_router.name == "ai_mode"
    except Exception as e:
        errors.append(f"bot.handlers.ai_mode: {e}")

    if errors:
        for err in errors:
            print(f"FAIL: {err}", file=sys.stderr)
        return 1
    print("OK: all import checks passed.")
    return 0

if __name__ == "__main__":
    sys.exit(main())
