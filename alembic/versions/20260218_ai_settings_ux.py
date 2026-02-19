"""AI settings UX: context_mode, message_mode, response_delay, min_pause, handoff, ai_paused

Revision ID: 20260218_ai_ux
Revises: 20260218_profile_ai
Create Date: 2026-02-18

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260218_ai_ux"
down_revision: Union[str, None] = "20260218_profile_ai"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "ai_settings",
        sa.Column("context_mode", sa.String(length=20), nullable=False, server_default="last_n"),
    )
    op.add_column(
        "ai_settings",
        sa.Column("context_value", sa.Integer(), nullable=False, server_default=sa.text("20")),
    )
    op.add_column(
        "ai_settings",
        sa.Column("message_mode", sa.String(length=20), nullable=False, server_default="single"),
    )
    op.add_column(
        "ai_settings",
        sa.Column("message_sentences_count", sa.Integer(), nullable=True),
    )
    op.add_column(
        "ai_settings",
        sa.Column("response_delay_seconds", sa.Integer(), nullable=False, server_default=sa.text("10")),
    )
    op.add_column(
        "ai_settings",
        sa.Column("min_pause_seconds", sa.Integer(), nullable=False, server_default=sa.text("0")),
    )
    op.add_column(
        "ai_settings",
        sa.Column("stop_on_employee_message", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.add_column(
        "ai_settings",
        sa.Column("auto_return_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "ai_settings",
        sa.Column("auto_return_minutes", sa.Integer(), nullable=True),
    )
    op.add_column(
        "ai_dialog_state",
        sa.Column("ai_paused", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("ai_dialog_state", "ai_paused")
    op.drop_column("ai_settings", "auto_return_minutes")
    op.drop_column("ai_settings", "auto_return_enabled")
    op.drop_column("ai_settings", "stop_on_employee_message")
    op.drop_column("ai_settings", "min_pause_seconds")
    op.drop_column("ai_settings", "response_delay_seconds")
    op.drop_column("ai_settings", "message_sentences_count")
    op.drop_column("ai_settings", "message_mode")
    op.drop_column("ai_settings", "context_value")
    op.drop_column("ai_settings", "context_mode")
