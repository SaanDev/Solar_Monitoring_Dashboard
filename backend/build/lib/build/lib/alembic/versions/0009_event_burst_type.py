"""Burst type on events

Radio-burst events now carry the type CCMT assigned (Type II / Type III /
Other), so the Timeline can color the model lane the same way it colors the
official burst-list lane. The description already mentions the type for humans;
this is the structured field the UI reads, rather than parsing prose.

Null is meaningful and common: typing was off, or no region inside the burst was
in CCMT's training distribution. Those events stay in the lane's neutral color
rather than being guessed at.

Revision ID: 0009
Revises: 0008
Create Date: 2026-07-30
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0009"
down_revision: Union[str, None] = "0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("events", sa.Column("burst_type", sa.String(length=16), nullable=True))


def downgrade() -> None:
    op.drop_column("events", "burst_type")
