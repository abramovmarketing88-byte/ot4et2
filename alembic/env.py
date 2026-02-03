"""Alembic env: sync engine only (no async URL)."""
import logging
from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine
from sqlalchemy.engine import Connection

from core.config import settings
from core.database.models import Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

# Sync URL for Alembic: MUST NOT use postgresql+asyncpg (causes super().__init__ etc.)
# Replace '+asyncpg' with '' so we get standard postgresql:// (sync driver).
_raw_url = settings.DATABASE_URL
if "+asyncpg" in _raw_url:
    db_url = _raw_url.replace("+asyncpg", "")
else:
    db_url = _raw_url.replace("+aiosqlite", "").replace("sqlite+aiosqlite", "sqlite")


def _mask_url(url: str) -> str:
    """Mask password in URL for logging."""
    try:
        from urllib.parse import urlparse, urlunparse
        p = urlparse(url)
        if p.password:
            netloc = p.hostname or ""
            if p.port:
                netloc += f":{p.port}"
            if p.username:
                netloc = f"{p.username}:****@{netloc}"
            else:
                netloc = f"****@{netloc}"
            return urlunparse((p.scheme, netloc, p.path or "", "", "", ""))
    except Exception:
        return url[:50] + "..." if len(url) > 50 else "***"


logging.getLogger("alembic.env").info(
    "Alembic using sync URL: %s", _mask_url(db_url)
)


def run_migrations_offline() -> None:
    context.configure(url=db_url, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = create_engine(db_url)
    with connectable.connect() as connection:
        do_run_migrations(connection)
    connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
