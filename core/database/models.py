"""
Async SQLAlchemy 2.0 models: User, AvitoProfile, ReportTask.

Все datetime в БД хранятся в UTC (см. core.timezone.utc_now).
"""
from datetime import datetime, time
from typing import Optional

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, String, Text, Time
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    telegram_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    current_mode: Mapped[str] = mapped_column(String(20), default="reporting")
    current_branch_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

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

    # ─── Report scheduling (flexible) ─────────────────────────────────────
    # report_frequency: 'daily' | 'interval' | 'weekly' | 'monthly'
    report_frequency: Mapped[str] = mapped_column(String(20), default="daily")
    # For 'interval': send every N days
    report_interval_value: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    # For 'weekly': comma-separated weekdays, e.g. '0,2,4' for Mon, Wed, Fri (0=Mon..6=Sun)
    report_weekdays: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    # Time of day to send (stored in profile timezone for display; execution uses report_timezone)
    report_time: Mapped[time] = mapped_column(Time, default=time(9, 0))
    report_timezone: Mapped[str] = mapped_column(String(50), default="UTC")
    is_report_active: Mapped[bool] = mapped_column(Boolean, default=True)

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
    # Настройки расписания: дни недели (0=Пн..6=Вс), JSON-массив, напр. [0,1,2,3,4]
    report_days: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # Период отчёта: "day" | "week" | "month"
    report_period: Mapped[str] = mapped_column(String(10), default="day")

    profile: Mapped["AvitoProfile"] = relationship(
        "AvitoProfile", back_populates="report_tasks"
    )


class PromptTemplate(Base):
    __tablename__ = "prompt_templates"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    owner_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.telegram_id", ondelete="CASCADE")
    )
    name: Mapped[str] = mapped_column(String(255))
    scope: Mapped[str] = mapped_column(String(20))
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )


class AIBranch(Base):
    __tablename__ = "ai_branches"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    owner_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.telegram_id", ondelete="CASCADE")
    )
    name: Mapped[str] = mapped_column(String(255))
    avito_profile_id: Mapped[int] = mapped_column(
        ForeignKey("avito_profiles.id", ondelete="CASCADE")
    )
    gpt_model: Mapped[str] = mapped_column(String(20))
    system_prompt_id: Mapped[int] = mapped_column(
        ForeignKey("prompt_templates.id", ondelete="RESTRICT")
    )
    context_retention_days: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    max_messages_in_context: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    followup_enabled: Mapped[bool] = mapped_column(Boolean, default=False)


class AIDialogMessage(Base):
    __tablename__ = "ai_dialog_messages"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.telegram_id", ondelete="CASCADE")
    )
    branch_id: Mapped[int] = mapped_column(
        ForeignKey("ai_branches.id", ondelete="CASCADE")
    )
    dialog_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    role: Mapped[str] = mapped_column(String(20))
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class FollowupChain(Base):
    __tablename__ = "followup_chains"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    branch_id: Mapped[int] = mapped_column(
        ForeignKey("ai_branches.id", ondelete="CASCADE")
    )
    name: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    start_event: Mapped[str] = mapped_column(String(30))
    stop_on_conversion: Mapped[bool] = mapped_column(Boolean, default=True)


class FollowupStep(Base):
    __tablename__ = "followup_steps"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    chain_id: Mapped[int] = mapped_column(
        ForeignKey("followup_chains.id", ondelete="CASCADE")
    )
    order_index: Mapped[int] = mapped_column(Integer)
    delay_seconds: Mapped[int] = mapped_column(Integer)
    send_mode: Mapped[str] = mapped_column(String(50))
    content_type: Mapped[str] = mapped_column(String(20))
    fixed_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    prompt_template_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("prompt_templates.id", ondelete="SET NULL"), nullable=True
    )
    target_channel: Mapped[str] = mapped_column(String(30))


class ScheduledFollowup(Base):
    __tablename__ = "scheduled_followups"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.telegram_id", ondelete="CASCADE")
    )
    branch_id: Mapped[int] = mapped_column(
        ForeignKey("ai_branches.id", ondelete="CASCADE")
    )
    chain_id: Mapped[int] = mapped_column(
        ForeignKey("followup_chains.id", ondelete="CASCADE")
    )
    step_id: Mapped[int] = mapped_column(
        ForeignKey("followup_steps.id", ondelete="CASCADE")
    )
    dialog_id: Mapped[str] = mapped_column(String(255))
    execute_at: Mapped[datetime] = mapped_column(DateTime)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    converted: Mapped[bool] = mapped_column(Boolean, default=False)
    negative_detected: Mapped[bool] = mapped_column(Boolean, default=False)


class AIDialogState(Base):
    __tablename__ = "ai_dialog_state"

    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.telegram_id", ondelete="CASCADE"), primary_key=True
    )
    branch_id: Mapped[int] = mapped_column(
        ForeignKey("ai_branches.id", ondelete="CASCADE"), primary_key=True
    )
    dialog_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    is_converted: Mapped[bool] = mapped_column(Boolean, default=False)
    has_negative: Mapped[bool] = mapped_column(Boolean, default=False)
    phone_number: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    last_client_message_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
