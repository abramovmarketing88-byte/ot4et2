"""Конфигурация из переменных окружения."""
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

    # Worker: retry и таймауты (опционально через env)
    WORKER_STARTUP_TIMEOUT_SEC: int = 60
    WORKER_STARTUP_RETRIES: int = 5
    WORKER_POLLING_RETRIES: int = 10
    WORKER_RETRY_BACKOFF_BASE_SEC: int = 5
    WORKER_RETRY_BACKOFF_MAX_SEC: int = 300

    @field_validator("ADMIN_CHAT_ID", mode="before")
    @classmethod
    def empty_admin_chat(cls, v: str | int | None) -> int | None:
        if v is None or v == "":
            return None
        if isinstance(v, str) and not v.strip():
            return None
        return int(v) if isinstance(v, str) else v


settings = Settings()
