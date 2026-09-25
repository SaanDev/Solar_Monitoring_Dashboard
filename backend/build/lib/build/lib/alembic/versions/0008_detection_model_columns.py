"""Model provenance and burst type on radio_burst_detections

Several burst classifiers can now score a segment (CCM v1.0.0 / v1.1.0), and a
second stage (CCMT v1.0.0) can label the burst's type. A row therefore has to
record *which* model produced it, otherwise a change of the configured scan model
silently mixes incomparable verdicts in the same table.

``filename`` stays the primary key: the automatic scan runs exactly one binary
model at a time, so there is at most one row per archive file and re-scoring with
a different model replaces it in place. Existing rows all came from CCM v1.0.0,
which is what the server default backfills.

Revision ID: 0008
Revises: 0007
Create Date: 2026-07-30
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0008"
down_revision: Union[str, None] = "0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "radio_burst_detections",
        sa.Column(
            "model_id",
            sa.String(length=32),
            nullable=False,
            server_default="ccm-1.0.0",
        ),
    )
    # Burst type is null whenever typing was off, the file is not a burst, or no
    # region cleared the type stage's in-distribution floors.
    op.add_column(
        "radio_burst_detections", sa.Column("burst_type", sa.String(length=16), nullable=True)
    )
    op.add_column(
        "radio_burst_detections", sa.Column("type_confidence", sa.Float(), nullable=True)
    )
    op.add_column(
        "radio_burst_detections", sa.Column("type_model_id", sa.String(length=32), nullable=True)
    )
    # The scanner's dedup query filters on (start_time, model_id).
    op.create_index(
        "ix_radio_burst_detections_model_id", "radio_burst_detections", ["model_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_radio_burst_detections_model_id", table_name="radio_burst_detections")
    op.drop_column("radio_burst_detections", "type_model_id")
    op.drop_column("radio_burst_detections", "type_confidence")
    op.drop_column("radio_burst_detections", "burst_type")
    op.drop_column("radio_burst_detections", "model_id")
