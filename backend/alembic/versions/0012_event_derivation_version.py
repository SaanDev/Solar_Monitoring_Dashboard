"""Event derivation version marker

Events (flares, proton events, Kp/Dst storms) are derived from the stored
time-series, but each detection pass only re-derives a recent window, so
history keeps whatever an older detector — or data since revised upstream —
once produced. The version of the detection logic that last re-derived the
stored history is recorded here; on startup a database at an older version
re-derives its stored events from the time-series once, then is marked current.

Existing rows start at 0, so every database re-derives its history once.

Revision ID: 0012
Revises: 0011
Create Date: 2026-10-02
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0012"
down_revision: Union[str, None] = "0011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "app_settings",
        sa.Column("event_derivation_version", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("app_settings", "event_derivation_version")
