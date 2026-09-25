"""Per-day coverage ledger for ML burst detection over the e-CALLISTO archive.

The live scanner only ever looks at the last few hours (``radio_burst_max_age_hours``),
so every hour the dashboard is offline is an hour of archive nobody scores — a
permanent hole in the Timeline and the correlation histograms. The catch-up pass
(``app/services/radio_backfill_service.py``) closes those holes, and this table is
how it knows where they are.

One row per UTC day:

* ``archive_files`` — segments e-CALLISTO published that day (from the directory
  listing), i.e. how much there is to score.
* ``covered_files`` — segments that have a row in ``radio_burst_detections``,
  **by any model**: a day scored by an older classifier still counts as covered,
  so switching models does not re-open 30 days of work.
* ``state`` — ``done`` when the day is fully covered, ``partial`` when some files
  are still missing (typically the current day, still being published), ``error``
  when the archive or inference failed. Only ``done`` days are skipped without any
  network call, which is what keeps the hourly gap check cheap.

The table is a *cache of coverage*, never a source of truth: deleting it costs one
listing fetch per day to rebuild, and the detection rows themselves are untouched.
"""
from datetime import date as date_cls, datetime, timezone

from sqlalchemy import Date, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base, UTCDateTime

# Day states. `pending` is a day known to need work that has not been attempted
# yet; `running` is the day the current job is on (so a crash mid-day is visible).
STATE_PENDING = "pending"
STATE_RUNNING = "running"
STATE_DONE = "done"
STATE_PARTIAL = "partial"
STATE_ERROR = "error"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class RadioBurstBackfillDay(Base):
    __tablename__ = "radio_burst_backfill_days"

    # UTC day this row describes.
    day: Mapped[date_cls] = mapped_column(Date, primary_key=True)
    state: Mapped[str] = mapped_column(
        String(16), nullable=False, default=STATE_PENDING
    )
    # Segments the archive lists for the day; 0 until the day has been inspected.
    archive_files: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Segments with a detection row (any model) — coverage, not this run's work.
    covered_files: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Files this backfill actually scored / failed to score on its last attempt.
    scored_files: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed_files: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # radio_burst events standing for the day after the last rebuild.
    events: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Binary classifier used on the last attempt (empty before any attempt).
    model_id: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(
        UTCDateTime(), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), default=_utcnow, onupdate=_utcnow, nullable=False
    )
