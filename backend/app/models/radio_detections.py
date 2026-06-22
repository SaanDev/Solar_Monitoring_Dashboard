"""Per-file ML burst-detection record.

One row per e-CALLISTO ``.fit.gz`` segment the model has scored. The table is
both an **audit trail** (every scored file, its probability and verdict) and the
**dedup registry** for the scanner: a filename already present here is not
re-downloaded or re-scored. ``radio_burst`` events shown in the alert feed are
*aggregated* from the burst-positive rows here, grouped by 15-minute window.

``filename`` is globally unique in the e-CALLISTO archive
(``STATION_YYYYMMDD_HHMMSS_NN.fit.gz``), so it serves as the primary key.
"""
from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class RadioBurstDetection(Base):
    __tablename__ = "radio_burst_detections"

    # Archive filename, e.g. "SRI-Lanka_20260618_213000_01.fit.gz".
    filename: Mapped[str] = mapped_column(String(128), primary_key=True)
    station: Mapped[str] = mapped_column(String(64), nullable=False)
    # Segment start (from the filename / FITS header); ~15 min long.
    start_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    end_time: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    focus: Mapped[str] = mapped_column(String(8), nullable=False, default="")
    # Sigmoid output in [0, 1] and the model's verdict at its tuned threshold.
    probability: Mapped[float] = mapped_column(Float, nullable=False)
    predicted_label: Mapped[str] = mapped_column(String(16), nullable=False)
    # Human-facing band: "High-confidence burst" | "Likely burst" | ...
    alert_level: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    processed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )
