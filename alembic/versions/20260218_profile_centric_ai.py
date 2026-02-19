"""profile-centric ai consolidation

Revision ID: 20260218_profile_ai
Revises: 20260218_ai_seller
Create Date: 2026-02-18
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260218_profile_ai"
down_revision: Union[str, None] = "20260218_ai_seller"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "ai_settings",
        sa.Column("profile_id", sa.Integer(), sa.ForeignKey("avito_profiles.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("system_prompt", sa.Text(), nullable=True),
        sa.Column("model_alias", sa.String(length=40), nullable=False, server_default="gpt-4o-mini"),
        sa.Column("max_messages_in_context", sa.Integer(), nullable=True),
        sa.Column("context_retention_days", sa.Integer(), nullable=True),
        sa.Column("daily_dialog_limit", sa.Integer(), nullable=False, server_default="50"),
        sa.Column("per_dialog_message_limit", sa.Integer(), nullable=False, server_default="20"),
        sa.Column("messages_per_minute_limit", sa.Integer(), nullable=False, server_default="10"),
        sa.Column("cooldown_after_n_messages", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("cooldown_minutes", sa.Integer(), nullable=False, server_default="2"),
        sa.Column("block_on_limit", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("stop_words", sa.Text(), nullable=True),
        sa.Column("negative_phrases", sa.Text(), nullable=True),
        sa.Column("stop_on_negative", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("summary_mode", sa.String(length=30), nullable=False, server_default="off"),
        sa.Column("summary_timeout_minutes", sa.Integer(), nullable=True),
        sa.Column("summary_message_threshold", sa.Integer(), nullable=True),
        sa.Column("summary_target_chat_id", sa.BigInteger(), nullable=True),
        sa.Column("summary_include_phone", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("summary_include_transcript", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("employee_ids", sa.Text(), nullable=True),
        sa.Column("notify_employee_on_conversion", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("delegate_on_stop", sa.Boolean(), nullable=False, server_default=sa.false()),
    )

    # Create AI settings from branches before dropping ai_branches.
    op.execute(
        """
        INSERT INTO ai_settings (profile_id, is_enabled, system_prompt, model_alias, max_messages_in_context, context_retention_days)
        SELECT b.avito_profile_id,
               COALESCE(b.followup_enabled, FALSE),
               p.content,
               CASE
                 WHEN b.gpt_model='gpt-mini' THEN 'gpt-4o-mini'
                 WHEN b.gpt_model='gpt-mid' THEN 'gpt-4o-mini'
                 WHEN b.gpt_model='gpt-optimal' THEN 'gpt-4o-mini'
                 WHEN b.gpt_model='gpt-pro' THEN 'gpt-4o-mini'
                 ELSE 'gpt-4o-mini'
               END,
               b.max_messages_in_context,
               b.context_retention_days
        FROM ai_branches b
        LEFT JOIN prompt_templates p ON p.id=b.system_prompt_id
        WHERE NOT EXISTS (SELECT 1 FROM ai_settings s WHERE s.profile_id=b.avito_profile_id)
        """
    )

    op.add_column("ai_dialog_messages", sa.Column("profile_id", sa.Integer(), nullable=True))
    op.execute("UPDATE ai_dialog_messages m SET profile_id = (SELECT avito_profile_id FROM ai_branches b WHERE b.id=m.branch_id)")

    op.add_column("ai_dialog_state", sa.Column("profile_id", sa.Integer(), nullable=True))
    op.execute("UPDATE ai_dialog_state s SET profile_id = (SELECT avito_profile_id FROM ai_branches b WHERE b.id=s.branch_id)")

    op.add_column("followup_steps", sa.Column("profile_id", sa.Integer(), nullable=True))
    op.add_column("followup_steps", sa.Column("content_text", sa.Text(), nullable=True))
    op.add_column("followup_steps", sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.execute("UPDATE followup_steps fs SET profile_id=(SELECT branch.avito_profile_id FROM followup_chains ch JOIN ai_branches branch ON branch.id=ch.branch_id WHERE ch.id=fs.chain_id)")
    op.execute("UPDATE followup_steps SET content_text=fixed_text")

    op.add_column("scheduled_followups", sa.Column("profile_id", sa.Integer(), nullable=True))
    op.execute("UPDATE scheduled_followups sf SET profile_id = (SELECT avito_profile_id FROM ai_branches b WHERE b.id=sf.branch_id)")

    # Drop old branch-centric structures only after migration.
    op.drop_constraint("scheduled_followups_chain_id_fkey", "scheduled_followups", type_="foreignkey")
    op.drop_column("scheduled_followups", "chain_id")
    op.drop_constraint("scheduled_followups_branch_id_fkey", "scheduled_followups", type_="foreignkey")
    op.drop_column("scheduled_followups", "branch_id")

    op.drop_constraint("ai_dialog_messages_branch_id_fkey", "ai_dialog_messages", type_="foreignkey")
    op.drop_column("ai_dialog_messages", "branch_id")

    op.drop_constraint("followup_steps_chain_id_fkey", "followup_steps", type_="foreignkey")
    op.drop_column("followup_steps", "chain_id")
    op.drop_column("followup_steps", "fixed_text")
    op.drop_column("followup_steps", "prompt_template_id")
    op.drop_column("followup_steps", "target_channel")

    op.drop_constraint("ai_dialog_state_branch_id_fkey", "ai_dialog_state", type_="foreignkey")
    op.drop_column("ai_dialog_state", "branch_id")

    op.drop_table("followup_chains")
    op.drop_table("ai_branches")


def downgrade() -> None:
    raise RuntimeError("Downgrade not supported for profile-centric AI consolidation")
