"""initial schema: time-series tables + source_status + TimescaleDB hypertables

Revision ID: 0001
Revises:
Create Date: 2026-06-16
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Numeric time-series tables — created with the same shape, differing only in
# their value columns. Each gets a composite PK (time, source) and becomes a
# TimescaleDB hypertable partitioned on `time`.
_HYPERTABLES = ("goes_xrs", "goes_proton", "kp_index", "dst_index")


def _ingest_columns() -> list[sa.Column]:
    return [
        sa.Column("time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("ingested_at", sa.DateTime(timezone=True), nullable=False),
    ]


def upgrade() -> None:
    op.create_table(
        "goes_xrs",
        *_ingest_columns(),
        sa.Column("satellite", sa.Integer(), nullable=True),
        sa.Column("short_channel", sa.Float(), nullable=True),
        sa.Column("long_channel", sa.Float(), nullable=True),
        sa.PrimaryKeyConstraint("time", "source"),
    )
    op.create_table(
        "goes_proton",
        *_ingest_columns(),
        sa.Column("satellite", sa.Integer(), nullable=True),
        sa.Column("flux_gt10", sa.Float(), nullable=True),
        sa.Column("flux_gt50", sa.Float(), nullable=True),
        sa.Column("flux_gt100", sa.Float(), nullable=True),
        sa.PrimaryKeyConstraint("time", "source"),
    )
    op.create_table(
        "kp_index",
        *_ingest_columns(),
        sa.Column("kp", sa.Float(), nullable=False),
        sa.PrimaryKeyConstraint("time", "source"),
    )
    op.create_table(
        "dst_index",
        *_ingest_columns(),
        sa.Column("dst", sa.Float(), nullable=False),
        sa.PrimaryKeyConstraint("time", "source"),
    )
    op.create_table(
        "source_status",
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("name"),
    )

    # Promote the time-series tables to TimescaleDB hypertables. Guarded so the
    # migration still succeeds on a vanilla PostgreSQL instance without the
    # extension (the tables remain ordinary tables in that case).
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("CREATE EXTENSION IF NOT EXISTS timescaledb")
        for table in _HYPERTABLES:
            op.execute(
                f"SELECT create_hypertable('{table}', 'time', "
                "if_not_exists => TRUE, migrate_data => TRUE)"
            )


def downgrade() -> None:
    for table in ("source_status", "dst_index", "kp_index", "goes_proton", "goes_xrs"):
        op.drop_table(table)
