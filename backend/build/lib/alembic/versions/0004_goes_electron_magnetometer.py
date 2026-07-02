"""GOES electron flux + magnetometer time-series tables

Adds two real-time GOES products with the same ``(time, source)`` shape as the
existing series and promotes them to TimescaleDB hypertables.

Revision ID: 0004
Revises: 0003
Create Date: 2026-06-23
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_HYPERTABLES = ("goes_electron", "goes_magnetometer")


def _ingest_columns() -> list[sa.Column]:
    return [
        sa.Column("time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("ingested_at", sa.DateTime(timezone=True), nullable=False),
    ]


def upgrade() -> None:
    op.create_table(
        "goes_electron",
        *_ingest_columns(),
        sa.Column("satellite", sa.Integer(), nullable=True),
        sa.Column("flux_ge2mev", sa.Float(), nullable=True),
        sa.PrimaryKeyConstraint("time", "source"),
    )
    op.create_table(
        "goes_magnetometer",
        *_ingest_columns(),
        sa.Column("satellite", sa.Integer(), nullable=True),
        sa.Column("hp", sa.Float(), nullable=True),
        sa.Column("he", sa.Float(), nullable=True),
        sa.Column("hn", sa.Float(), nullable=True),
        sa.Column("total", sa.Float(), nullable=True),
        sa.PrimaryKeyConstraint("time", "source"),
    )

    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        for table in _HYPERTABLES:
            op.execute(
                f"SELECT create_hypertable('{table}', 'time', "
                "if_not_exists => TRUE, migrate_data => TRUE)"
            )


def downgrade() -> None:
    for table in ("goes_magnetometer", "goes_electron"):
        op.drop_table(table)
