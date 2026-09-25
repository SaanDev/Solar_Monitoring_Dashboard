"""Alert-delivery tables: notification settings + sent-notification ledger

Revision ID: 0006
Revises: 0005
Create Date: 2026-07-04
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "notification_settings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("telegram_enabled", sa.Boolean(), nullable=False),
        sa.Column("telegram_chat_id", sa.String(length=64), nullable=False),
        sa.Column("webhook_enabled", sa.Boolean(), nullable=False),
        sa.Column("webhook_url", sa.Text(), nullable=False),
        sa.Column("min_severity", sa.String(length=16), nullable=False),
        sa.Column("event_types", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "sent_notifications",
        sa.Column("event_id", sa.String(length=128), nullable=False),
        sa.Column("severity", sa.String(length=16), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("event_id"),
    )


def downgrade() -> None:
    op.drop_table("sent_notifications")
    op.drop_table("notification_settings")
