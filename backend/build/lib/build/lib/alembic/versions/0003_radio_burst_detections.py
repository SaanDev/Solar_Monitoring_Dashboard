"""radio_burst_detections table: per-file ML burst classifier results

One row per scored e-CALLISTO segment. Doubles as the scanner's dedup registry
and the source for aggregated ``radio_burst`` events. Like ``events`` it is a
sparse, time-range-queried table, so it stays an ordinary table (no hypertable).

Revision ID: 0003
Revises: 0002
Create Date: 2026-06-19
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "radio_burst_detections",
        sa.Column("filename", sa.String(length=128), nullable=False),
        sa.Column("station", sa.String(length=64), nullable=False),
        sa.Column("start_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("focus", sa.String(length=8), nullable=False),
        sa.Column("probability", sa.Float(), nullable=False),
        sa.Column("predicted_label", sa.String(length=16), nullable=False),
        sa.Column("alert_level", sa.String(length=32), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("filename"),
    )
    # Dedup and aggregation both filter by segment start time.
    op.create_index(
        "ix_radio_burst_detections_start_time",
        "radio_burst_detections",
        ["start_time"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_radio_burst_detections_start_time",
        table_name="radio_burst_detections",
    )
    op.drop_table("radio_burst_detections")
