"""Coronal mass ejection ORM model (NASA DONKI catalog).

Unlike the numeric time-series, CMEs are discrete catalog entries keyed by
DONKI's ``activityID`` — re-ingesting the same window upserts the analyst's
latest measurement/model run in place (analyses are revised for days after an
eruption), never duplicating an event. Earth-directed entries additionally
surface through the shared ``events`` table (type ``"cme"``) so they reach the
alert feed; this table keeps the full catalog including non-Earth-directed CMEs.
"""
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class CmeEvent(Base):
    __tablename__ = "cme_events"

    # DONKI activity id, e.g. "2026-06-24T13:00:00-CME-001".
    activity_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    start_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    # Heliographic source region, e.g. "S09E32"; NOAA active-region number.
    source_location: Mapped[str | None] = mapped_column(String(16), nullable=True)
    active_region: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Operative analyst fit (the ``isMostAccurate`` analysis): cone-model
    # direction/width plus radial speed at 21.5 solar radii.
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    half_angle: Mapped[float | None] = mapped_column(Float, nullable=True)
    speed: Mapped[float | None] = mapped_column(Float, nullable=True)
    cme_type: Mapped[str | None] = mapped_column(String(8), nullable=True)
    time21_5: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # WSA-ENLIL model run: predicted Earth shock arrival and the run's max
    # predicted Kp. ``is_earth_directed`` = the model predicts an Earth arrival.
    is_earth_directed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    predicted_arrival_time: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    predicted_kp: Mapped[float | None] = mapped_column(Float, nullable=True)

    note: Mapped[str] = mapped_column(Text, nullable=False, default="")
    catalog_link: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )
