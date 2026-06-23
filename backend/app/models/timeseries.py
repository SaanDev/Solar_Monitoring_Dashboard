"""Time-series ORM models, one table per numeric product.

Each table uses a composite primary key ``(time, source)`` so re-ingesting the
same point is an idempotent upsert (never a duplicate), and so ``time`` is part
of the key — a requirement for TimescaleDB hypertables. ``source`` records data
provenance (e.g. real-time NOAA vs. Kyoto quicklook) so feeds are never silently
mixed (see ``AGENT_RULES.md``).
"""
from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class _IngestMixin:
    # Provenance + when this row was written, stored with every product.
    source: Mapped[str] = mapped_column(String(64), primary_key=True)
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )


class GoesXrs(_IngestMixin, Base):
    __tablename__ = "goes_xrs"

    time: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    satellite: Mapped[int | None] = mapped_column(Integer, nullable=True)
    short_channel: Mapped[float | None] = mapped_column(Float, nullable=True)
    long_channel: Mapped[float | None] = mapped_column(Float, nullable=True)


class GoesProton(_IngestMixin, Base):
    __tablename__ = "goes_proton"

    time: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    satellite: Mapped[int | None] = mapped_column(Integer, nullable=True)
    flux_gt10: Mapped[float | None] = mapped_column(Float, nullable=True)
    flux_gt50: Mapped[float | None] = mapped_column(Float, nullable=True)
    flux_gt100: Mapped[float | None] = mapped_column(Float, nullable=True)


class GoesElectron(_IngestMixin, Base):
    __tablename__ = "goes_electron"

    time: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    satellite: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Integral electron flux >=2 MeV (electrons / cm^2 s sr). NOAA's primary feed
    # exposes only this energy band.
    flux_ge2mev: Mapped[float | None] = mapped_column(Float, nullable=True)


class GoesMagnetometer(_IngestMixin, Base):
    __tablename__ = "goes_magnetometer"

    time: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    satellite: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Geomagnetic field components at the satellite (nT): Hp (northward),
    # He (earthward), Hn (eastward), and the total field magnitude.
    hp: Mapped[float | None] = mapped_column(Float, nullable=True)
    he: Mapped[float | None] = mapped_column(Float, nullable=True)
    hn: Mapped[float | None] = mapped_column(Float, nullable=True)
    total: Mapped[float | None] = mapped_column(Float, nullable=True)


class KpIndex(_IngestMixin, Base):
    __tablename__ = "kp_index"

    time: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    kp: Mapped[float] = mapped_column(Float, nullable=False)


class DstIndex(_IngestMixin, Base):
    __tablename__ = "dst_index"

    time: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    dst: Mapped[float] = mapped_column(Float, nullable=False)


# Tables that should become TimescaleDB hypertables (partitioned on ``time``).
HYPERTABLES = (
    "goes_xrs",
    "goes_proton",
    "goes_electron",
    "goes_magnetometer",
    "kp_index",
    "dst_index",
)
