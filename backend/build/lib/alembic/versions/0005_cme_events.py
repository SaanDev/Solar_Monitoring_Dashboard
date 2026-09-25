"""CME catalog table (NASA DONKI)

Discrete catalog entries keyed by DONKI activity id — a plain table (not a
hypertable): a solar cycle produces only thousands of rows.

Revision ID: 0005
Revises: 0004
Create Date: 2026-07-04
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "cme_events",
        sa.Column("activity_id", sa.String(length=64), nullable=False),
        sa.Column("start_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_location", sa.String(length=16), nullable=True),
        sa.Column("active_region", sa.Integer(), nullable=True),
        sa.Column("latitude", sa.Float(), nullable=True),
        sa.Column("longitude", sa.Float(), nullable=True),
        sa.Column("half_angle", sa.Float(), nullable=True),
        sa.Column("speed", sa.Float(), nullable=True),
        sa.Column("cme_type", sa.String(length=8), nullable=True),
        sa.Column("time21_5", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_earth_directed", sa.Boolean(), nullable=False),
        sa.Column("predicted_arrival_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("predicted_kp", sa.Float(), nullable=True),
        sa.Column("note", sa.Text(), nullable=False),
        sa.Column("catalog_link", sa.Text(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("activity_id"),
    )
    op.create_index("ix_cme_events_start_time", "cme_events", ["start_time"])


def downgrade() -> None:
    op.drop_index("ix_cme_events_start_time", table_name="cme_events")
    op.drop_table("cme_events")
