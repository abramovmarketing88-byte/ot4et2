"""Async SQLAlchemy 2.0 engine and sessionmaker. Main app uses postgresql+asyncpg."""
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from core.config import settings
from core.database.models import Base

logger = logging.getLogger(__name__)

# Main app: keep postgresql+asyncpg for AsyncSession (do not change to sync URL).
_url = settings.DATABASE_URL
if _url.startswith("sqlite"):
    Path("./data").mkdir(exist_ok=True)


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


_masked_url = _mask_url(_url)
print(f"Бот подключается к БД: {_masked_url}")
logger.info("AsyncSession использует URL: %s", _masked_url)

async_engine = create_async_engine(
    _url,
    echo=False,
    pool_pre_ping=not _url.startswith("sqlite"),
    connect_args={"check_same_thread": False} if "sqlite" in _url else {},
)

async_session_factory = async_sessionmaker(
    bind=async_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


@asynccontextmanager
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db() -> None:
    """Создание таблиц (для dev; в проде лучше через Alembic)."""
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # Добавить колонку report_metrics, если её нет (для существующих БД)
        def _add_report_metrics(connection: Any) -> None:
            from sqlalchemy import inspect, text
            insp = inspect(connection)
            if "report_tasks" in insp.get_table_names():
                cols = [c["name"] for c in insp.get_columns("report_tasks")]
                if "report_metrics" not in cols:
                    connection.execute(text("ALTER TABLE report_tasks ADD COLUMN report_metrics TEXT"))
        try:
            await conn.run_sync(_add_report_metrics)
        except Exception:
            pass
