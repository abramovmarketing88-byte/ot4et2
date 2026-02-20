"""Profile daily limits (CPX Promo): mon_penny..sun_penny, mode, apply job.

Revision ID: 20260220_daily_lim
Revises: 20260218_tg_int
Create Date: 2026-02-20

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260220_daily_lim"
down_revision: Union[str, None] = "20260218_tg_int"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "profile_daily_limits",
        sa.Column("profile_id", sa.Integer(), sa.ForeignKey("avito_profiles.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("mon_penny", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("tue_penny", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("wed_penny", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("thu_penny", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("fri_penny", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("sat_penny", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("sun_penny", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("mode", sa.String(20), nullable=False, server_default="auto_budget"),
        sa.Column("action_type_id", sa.Integer(), nullable=False, server_default=sa.text("5")),
        sa.Column("last_applied_date", sa.Date(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )


def downgrade() -> None:
    op.drop_table("profile_daily_limits")
