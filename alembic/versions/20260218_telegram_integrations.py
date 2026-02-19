"""Telegram integrations: telegram_targets, telegram_business_connections

Revision ID: 20260218_tg_int
Revises: 20260218_ai_ux
Create Date: 2026-02-18

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260218_tg_int"
down_revision: Union[str, None] = "20260218_ai_ux"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "telegram_targets",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("users.telegram_id", ondelete="CASCADE"), nullable=False),
        sa.Column("target_chat_id", sa.BigInteger(), nullable=False),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("welcome_message", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("ix_telegram_targets_user_id", "telegram_targets", ["user_id"])
    op.create_index("ix_telegram_targets_target_chat_id", "telegram_targets", ["target_chat_id"])

    op.create_table(
        "telegram_business_connections",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("users.telegram_id", ondelete="CASCADE"), nullable=False),
        sa.Column("connection_id", sa.String(255), nullable=False),
        sa.Column("business_user_id", sa.BigInteger(), nullable=False),
        sa.Column("user_chat_id", sa.BigInteger(), nullable=True),
        sa.Column("is_disabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("recipients_scope", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("ix_telegram_business_connections_user_id", "telegram_business_connections", ["user_id"])
    op.create_unique_constraint(
        "uq_telegram_business_connections_connection_id",
        "telegram_business_connections",
        ["connection_id"],
    )


def downgrade() -> None:
    op.drop_table("telegram_business_connections")
    op.drop_table("telegram_targets")
