"""Конфигурация из переменных окружения."""
import logging
import sys

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    BOT_TOKEN: str
    DATABASE_URL: str = "postgresql+asyncpg://user:pass@localhost:5432/avito_bot"
    AVITO_CLIENT_ID: str = ""
    AVITO_CLIENT_SECRET: str = ""
    AVITO_REDIRECT_URI: str = ""
    ADMIN_CHAT_ID: int | None = None
    LLM_API_KEY: str = ""
    OPENAI_API_KEY: str = ""  # альтернатива LLM_API_KEY (стандартное имя в OpenAI)

    # Worker: retry и таймауты (опционально через env)
    WORKER_STARTUP_TIMEOUT_SEC: int = 60
    WORKER_STARTUP_RETRIES: int = 5
    WORKER_POLLING_RETRIES: int = 10
    WORKER_RETRY_BACKOFF_BASE_SEC: int = 5
    WORKER_RETRY_BACKOFF_MAX_SEC: int = 300

    # Avito webhook server (messenger)
    AVITO_WEBHOOK_ENABLED: bool = False
    AVITO_WEBHOOK_HOST: str = "0.0.0.0"
    AVITO_WEBHOOK_PORT: int = 8000
    AVITO_WEBHOOK_PATH: str = "/avito/webhook"
    AVITO_WEBHOOK_SECRET: str | None = None

    @field_validator("ADMIN_CHAT_ID", mode="before")
    @classmethod
    def empty_admin_chat(cls, v: str | int | None) -> int | None:
        if v is None or v == "":
            return None
        if isinstance(v, str) and not v.strip():
            return None
        return int(v) if isinstance(v, str) else v


logger = logging.getLogger(__name__)

try:
    settings = Settings()
except Exception as e:
    # Частая причина: отсутствует BOT_TOKEN или неверный формат DATABASE_URL
    print(f">>> DEBUG: SETTINGS ERROR: {e}", file=sys.stderr, flush=True)
    logger.exception("Failed to load settings from environment")
    raise


LLM_MODEL_MAP: dict[str, str] = {
    "gpt-mini": "gpt-4o-mini",
    "gpt-mid": "gpt-4.1-mini",
    "gpt-optimal": "gpt-4.1",
    "gpt-pro": "gpt-4.1",
}
