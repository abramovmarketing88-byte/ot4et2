"""
Async SQLAlchemy 2.0 models: User, AvitoProfile, ReportTask.

Все datetime в БД хранятся в UTC (см. core.timezone.utc_now).
"""
from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    telegram_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)

    profiles: Mapped[list["AvitoProfile"]] = relationship(
        "AvitoProfile", back_populates="owner"
    )


class AvitoProfile(Base):
    __tablename__ = "avito_profiles"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    owner_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.telegram_id", ondelete="CASCADE")
    )
    profile_name: Mapped[str] = mapped_column(String(255))
    client_id: Mapped[str] = mapped_column(String(255))
    client_secret: Mapped[str] = mapped_column(String(255))
    user_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    access_token: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    token_expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True
    )  # UTC

    owner: Mapped["User"] = relationship("User", back_populates="profiles")
    report_tasks: Mapped[list["ReportTask"]] = relationship(
        "ReportTask", back_populates="profile"
    )


class ReportTask(Base):
    __tablename__ = "report_tasks"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    profile_id: Mapped[int] = mapped_column(
        ForeignKey("avito_profiles.id", ondelete="CASCADE")
    )
    chat_id: Mapped[int] = mapped_column(BigInteger)
    report_time: Mapped[str] = mapped_column(String(10), default="10:00")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    # JSON-массив ключей метрик для отчёта (пусто = все). Пример: ["views","contacts","total_spending","wallet_balance"]
    report_metrics: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    profile: Mapped["AvitoProfile"] = relationship(
        "AvitoProfile", back_populates="report_tasks"
    )
