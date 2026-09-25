"""Observing-stations column on events

Radio-burst events know which e-CALLISTO stations detected them; storing the
list (comma-separated) lets the UI restrict spectrograms to actual observers
instead of parsing the human-readable description.

Revision ID: 0007
Revises: 0006
Create Date: 2026-07-04
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0007"
down_revision: Union[str, None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("events", sa.Column("stations", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("events", "stations")
