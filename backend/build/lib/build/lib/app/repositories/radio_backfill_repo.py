"""Read/write helpers for the per-day backfill coverage ledger.

One row per UTC day (see ``app/models/radio_backfill.py``). Writes are
upsert-by-day so a re-attempt updates the day in place; reads are range scans the
Settings page's coverage strip and the hourly gap check both use.
"""
from __future__ import annotations

from datetime import date as date_cls, datetime, timezone

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.radio_backfill import RadioBurstBackfillDay

_FIELDS = (
    "state",
    "archive_files",
    "covered_files",
    "scored_files",
    "failed_files",
    "events",
    "model_id",
    "error",
    "completed_at",
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def to_dict(row: RadioBurstBackfillDay) -> dict:
    return {c.name: getattr(row, c.name) for c in RadioBurstBackfillDay.__table__.columns}


async def get_day(db: AsyncSession, day: date_cls) -> dict | None:
    row = await db.get(RadioBurstBackfillDay, day)
    return to_dict(row) if row is not None else None


async def upsert_day(db: AsyncSession, day: date_cls, **values) -> dict:
    """Create or update one day's coverage row; only the fields passed are touched.

    Done through the ORM rather than a dialect insert because these rows are
    written one at a time (once per day processed), and partial updates —
    "just move the state", "just bump the scored count" — read better this way.
    """
    row = await db.get(RadioBurstBackfillDay, day)
    if row is None:
        row = RadioBurstBackfillDay(day=day)
        db.add(row)
    for field in _FIELDS:
        if field in values:
            setattr(row, field, values[field])
    row.updated_at = _utcnow()
    await db.commit()
    await db.refresh(row)
    return to_dict(row)


async def days_in_range(
    db: AsyncSession, first: date_cls, last: date_cls
) -> dict[date_cls, dict]:
    """Coverage rows for ``[first, last]``, keyed by day (missing days absent)."""
    stmt = select(RadioBurstBackfillDay).where(
        and_(
            RadioBurstBackfillDay.day >= first,
            RadioBurstBackfillDay.day <= last,
        )
    )
    res = await db.execute(stmt)
    return {row.day: to_dict(row) for row in res.scalars().all()}
