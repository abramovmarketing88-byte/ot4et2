"""ai seller mode tables

Revision ID: 20260218_ai_seller
Revises: 20250206_flex
Create Date: 2026-02-18
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260218_ai_seller"
down_revision: Union[str, None] = "20250206_flex"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("current_mode", sa.String(length=20), nullable=False, server_default="reporting"))
    op.add_column("users", sa.Column("current_branch_id", sa.Integer(), nullable=True))

    op.create_table(
        "prompt_templates",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("owner_id", sa.BigInteger(), sa.ForeignKey("users.telegram_id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("scope", sa.String(length=20), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )

    op.create_table(
        "ai_branches",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("owner_id", sa.BigInteger(), sa.ForeignKey("users.telegram_id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("avito_profile_id", sa.Integer(), sa.ForeignKey("avito_profiles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("gpt_model", sa.String(length=20), nullable=False),
        sa.Column("system_prompt_id", sa.Integer(), sa.ForeignKey("prompt_templates.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("context_retention_days", sa.Integer(), nullable=True),
        sa.Column("max_messages_in_context", sa.Integer(), nullable=True),
        sa.Column("followup_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
    )

    op.create_table(
        "ai_dialog_messages",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("users.telegram_id", ondelete="CASCADE"), nullable=False),
        sa.Column("branch_id", sa.Integer(), sa.ForeignKey("ai_branches.id", ondelete="CASCADE"), nullable=False),
        sa.Column("dialog_id", sa.String(length=255), nullable=True),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )

    op.create_table(
        "followup_chains",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("branch_id", sa.Integer(), sa.ForeignKey("ai_branches.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("start_event", sa.String(length=30), nullable=False),
        sa.Column("stop_on_conversion", sa.Boolean(), nullable=False, server_default=sa.true()),
    )

    op.create_table(
        "followup_steps",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("chain_id", sa.Integer(), sa.ForeignKey("followup_chains.id", ondelete="CASCADE"), nullable=False),
        sa.Column("order_index", sa.Integer(), nullable=False),
        sa.Column("delay_seconds", sa.Integer(), nullable=False),
        sa.Column("send_mode", sa.String(length=50), nullable=False),
        sa.Column("content_type", sa.String(length=20), nullable=False),
        sa.Column("fixed_text", sa.Text(), nullable=True),
        sa.Column("prompt_template_id", sa.Integer(), sa.ForeignKey("prompt_templates.id", ondelete="SET NULL"), nullable=True),
        sa.Column("target_channel", sa.String(length=30), nullable=False),
    )

    op.create_table(
        "scheduled_followups",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("users.telegram_id", ondelete="CASCADE"), nullable=False),
        sa.Column("branch_id", sa.Integer(), sa.ForeignKey("ai_branches.id", ondelete="CASCADE"), nullable=False),
        sa.Column("chain_id", sa.Integer(), sa.ForeignKey("followup_chains.id", ondelete="CASCADE"), nullable=False),
        sa.Column("step_id", sa.Integer(), sa.ForeignKey("followup_steps.id", ondelete="CASCADE"), nullable=False),
        sa.Column("dialog_id", sa.String(length=255), nullable=False),
        sa.Column("execute_at", sa.DateTime(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("converted", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("negative_detected", sa.Boolean(), nullable=False, server_default=sa.false()),
    )

    op.create_table(
        "ai_dialog_state",
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("users.telegram_id", ondelete="CASCADE"), primary_key=True),
        sa.Column("branch_id", sa.Integer(), sa.ForeignKey("ai_branches.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("dialog_id", sa.String(length=255), primary_key=True),
        sa.Column("is_converted", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("has_negative", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("phone_number", sa.String(length=50), nullable=True),
        sa.Column("last_client_message_at", sa.DateTime(), nullable=True),
    )

    op.create_index(
        "ix_ai_dialog_messages_user_branch_created",
        "ai_dialog_messages",
        ["user_id", "branch_id", sa.text("created_at DESC")],
    )
    op.create_index(
        "ix_scheduled_followups_status_execute_at",
        "scheduled_followups",
        ["status", "execute_at"],
    )
    op.create_index(
        "ix_ai_dialog_state_user_branch_dialog",
        "ai_dialog_state",
        ["user_id", "branch_id", "dialog_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_ai_dialog_state_user_branch_dialog", table_name="ai_dialog_state")
    op.drop_index("ix_scheduled_followups_status_execute_at", table_name="scheduled_followups")
    op.drop_index("ix_ai_dialog_messages_user_branch_created", table_name="ai_dialog_messages")

    op.drop_table("ai_dialog_state")
    op.drop_table("scheduled_followups")
    op.drop_table("followup_steps")
    op.drop_table("followup_chains")
    op.drop_table("ai_dialog_messages")
    op.drop_table("ai_branches")
    op.drop_table("prompt_templates")

    op.drop_column("users", "current_branch_id")
    op.drop_column("users", "current_mode")
