"""Add report_days and report_period to report_tasks

Revision ID: 20250206_sched
Revises:
Create Date: 2025-02-06

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "20250206_sched"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "report_tasks",
        sa.Column("report_days", sa.Text(), nullable=True),
    )
    op.add_column(
        "report_tasks",
        sa.Column("report_period", sa.String(10), server_default=sa.text("'day'"), nullable=False),
    )


def downgrade() -> None:
    op.drop_column("report_tasks", "report_period")
    op.drop_column("report_tasks", "report_days")
