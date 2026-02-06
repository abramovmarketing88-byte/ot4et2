"""Added flexible reports and messenger export

Revision ID: 20250206_flex
Revises: 20250206_profile_sched
Create Date: 2025-02-06

Schema for flexible report scheduling and messenger export was added in
20250206_sched (report_tasks.report_days, report_period) and
20250206_profile_sched (avito_profiles.report_frequency, report_interval_value,
report_weekdays, report_time, report_timezone, is_report_active).
This revision documents the feature set; no further schema changes.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "20250206_flex"
down_revision: Union[str, None] = "20250206_profile_sched"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
