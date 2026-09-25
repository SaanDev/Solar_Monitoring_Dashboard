"""Runtime-editable application settings

Single-row table (id=1) backing the Settings page's burst-detection model
picker. Which classifier the automatic scan uses used to be environment-only
(``RADIO_BURST_BINARY_MODEL``), which meant editing .env and restarting; the
choice now persists here so it survives a restart and the scheduler picks it up.

An absent row (or an empty value) means "follow the configured default", so the
behaviour before this migration is preserved until someone actually chooses.

Revision ID: 0010
Revises: 0009
Create Date: 2026-08-02
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0010"
down_revision: Union[str, None] = "0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "app_settings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("radio_burst_binary_model", sa.String(length=64), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("app_settings")
