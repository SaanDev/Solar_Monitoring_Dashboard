"""events table: derived space-weather events (flares, SEP, geomagnetic storms)

The events table is sparse and queried by time range, not a high-rate time-series,
so it stays an ordinary table (no TimescaleDB hypertable). Idempotent detection
relies on the composite primary key ``(type, start_time)``.

Revision ID: 0002
Revises: 0001
Create Date: 2026-06-17
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "events",
        sa.Column("type", sa.String(length=32), nullable=False),
        sa.Column("start_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("peak_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("peak_value", sa.Float(), nullable=True),
        sa.Column("severity", sa.String(length=32), nullable=True),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("type", "start_time"),
    )
    # Events are listed newest-first over a date range; index the time column.
    op.create_index("ix_events_start_time", "events", ["start_time"])


def downgrade() -> None:
    op.drop_index("ix_events_start_time", table_name="events")
    op.drop_table("events")
