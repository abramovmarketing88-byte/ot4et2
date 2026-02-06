"""Add flexible report scheduling fields to avito_profiles

Revision ID: 20250206_profile_sched
Revises: 20250206_sched
Create Date: 2025-02-06

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "20250206_profile_sched"
down_revision: Union[str, None] = "20250206_sched"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "avito_profiles",
        sa.Column("report_frequency", sa.String(20), server_default=sa.text("'daily'"), nullable=False),
    )
    op.add_column(
        "avito_profiles",
        sa.Column("report_interval_value", sa.Integer(), nullable=True),
    )
    op.add_column(
        "avito_profiles",
        sa.Column("report_weekdays", sa.String(50), nullable=True),
    )
    op.add_column(
        "avito_profiles",
        sa.Column("report_time", sa.Time(), server_default=sa.text("'09:00'"), nullable=False),
    )
    op.add_column(
        "avito_profiles",
        sa.Column("report_timezone", sa.String(50), server_default=sa.text("'UTC'"), nullable=False),
    )
    op.add_column(
        "avito_profiles",
        sa.Column("is_report_active", sa.Boolean(), server_default=sa.true(), nullable=False),
    )


def downgrade() -> None:
    op.drop_column("avito_profiles", "is_report_active")
    op.drop_column("avito_profiles", "report_timezone")
    op.drop_column("avito_profiles", "report_time")
    op.drop_column("avito_profiles", "report_weekdays")
    op.drop_column("avito_profiles", "report_interval_value")
    op.drop_column("avito_profiles", "report_frequency")
