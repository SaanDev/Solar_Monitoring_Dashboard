"""Detected space-weather event ORM model.

Events are *derived* from the numeric time-series (X-ray flares, proton/SEP
events, geomagnetic storms) by the detection pass, then persisted here so the
Events page and alerts have stored history rather than recomputing on every
request.

The composite primary key ``(type, start_time)`` makes detection idempotent:
re-running the pass over an overlapping window upserts the same event in place
(extending ``end_time``/``peak`` as more data arrives) instead of duplicating it.
An event still in progress at the last sample has ``end_time`` left ``NULL``.
"""
from datetime import datetime, timezone

from sqlalchemy import Float, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base, UTCDateTime


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class SpaceWeatherEvent(Base):
    __tablename__ = "events"

    # ``type`` is a stable machine key (e.g. "xray_flare"); ``start_time`` anchors
    # the event so a still-growing event keeps the same identity across passes.
    type: Mapped[str] = mapped_column(String(32), primary_key=True)
    start_time: Mapped[datetime] = mapped_column(
        UTCDateTime(), primary_key=True
    )
    end_time: Mapped[datetime | None] = mapped_column(
        UTCDateTime(), nullable=True
    )
    peak_time: Mapped[datetime | None] = mapped_column(
        UTCDateTime(), nullable=True
    )
    peak_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    # Human-facing classification: flare class (e.g. "M1.2"), NOAA scale ("S2",
    # "G3"), or storm level ("Intense storm").
    severity: Mapped[str | None] = mapped_column(String(32), nullable=True)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # Observing stations (comma-separated) for station-based events (radio
    # bursts) — lets the UI show only spectrograms that actually saw the event.
    stations: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Radio bursts only: the type the burst-type classifier assigned ("Type II",
    # "Type III", "Other"). Null when typing was off or nothing in the burst was
    # classifiable — the Timeline colors those neutrally rather than guessing.
    burst_type: Mapped[str | None] = mapped_column(String(16), nullable=True)
    source: Mapped[str] = mapped_column(String(64), nullable=False, default="derived")
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), default=_utcnow, onupdate=_utcnow, nullable=False
    )
