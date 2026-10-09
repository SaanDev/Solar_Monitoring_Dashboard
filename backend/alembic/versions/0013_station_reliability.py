"""Multi-station burst confirmation: station reliability + derivation marker

``radio_station_reliability`` holds the daily per-station measurement that
weighs each station's readings in the burst confirmation, plus the operator's
override.

``app_settings.radio_burst_derivation_version`` records which version of the
burst-confirmation rule last re-derived the stored ``radio_burst`` events. Rows
start at 0, so every database rebuilds its burst history once with the new rule.

Revision ID: 0013
Revises: 0012
Create Date: 2026-10-08
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0013"
down_revision: Union[str, None] = "0012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "radio_station_reliability",
        sa.Column("station", sa.String(length=64), nullable=False),
        sa.Column("override", sa.String(length=8), nullable=False, server_default="auto"),
        sa.Column("model_id", sa.String(length=32), nullable=False, server_default=""),
        sa.Column("files", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("bursts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("judged", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("confirmed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("chance_rate", sa.Float(), nullable=True),
        sa.Column("score", sa.Float(), nullable=True),
        sa.Column("duty", sa.Float(), nullable=True),
        sa.Column("observed_minutes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("null_counts", sa.JSON(), nullable=True),
        sa.Column("anchor_counts", sa.JSON(), nullable=True),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("station"),
    )
    op.add_column(
        "app_settings",
        sa.Column("radio_burst_derivation_version", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("app_settings", "radio_burst_derivation_version")
    op.drop_table("radio_station_reliability")
