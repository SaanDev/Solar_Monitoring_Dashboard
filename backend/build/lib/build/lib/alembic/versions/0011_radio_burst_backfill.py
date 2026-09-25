"""Radio-burst offline catch-up: per-day coverage ledger

The live scanner only scores the last few hours, so downtime left permanent holes
in the burst timeline. The catch-up pass fills them; this table records, per UTC
day, how many segments the archive published and how many have been scored, so a
gap check costs one indexed query instead of re-listing the whole archive.

Coverage counting reads ``radio_burst_detections`` by segment start, which
migration 0003 already indexed.

Revision ID: 0011
Revises: 0010
Create Date: 2026-08-28
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0011"
down_revision: Union[str, None] = "0010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "radio_burst_backfill_days",
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("state", sa.String(length=16), nullable=False),
        sa.Column("archive_files", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("covered_files", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("scored_files", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failed_files", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("events", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("model_id", sa.String(length=32), nullable=False, server_default=""),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("day"),
    )


def downgrade() -> None:
    op.drop_table("radio_burst_backfill_days")
