"""Read/upsert helpers for the derived ``events`` table.

Upserts are idempotent on the composite key ``(type, start_time)`` — re-running
detection over an overlapping window updates an event in place (extending its
``end_time``/peak) rather than duplicating it.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.events import SpaceWeatherEvent

logger = logging.getLogger(__name__)

# Columns written from a detected-event dict; the rest (updated_at) are set here.
_EVENT_FIELDS = (
    "type",
    "start_time",
    "end_time",
    "peak_time",
    "peak_value",
    "severity",
    "description",
    "source_url",
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _insert(db: AsyncSession):
    fn = sqlite_insert if db.bind.dialect.name == "sqlite" else pg_insert
    return fn(SpaceWeatherEvent)


def _to_dict(obj: SpaceWeatherEvent) -> dict:
    return {c.name: getattr(obj, c.name) for c in SpaceWeatherEvent.__table__.columns}


async def upsert_events(
    db: AsyncSession, events: list[dict], source: str = "derived"
) -> int:
    """Insert/update detected ``events``; returns the number written."""
    if not events:
        return 0
    now = _utcnow()
    values = [
        {
            **{f: e.get(f) for f in _EVENT_FIELDS},
            "source": source,
            "updated_at": now,
        }
        for e in events
    ]
    stmt = _insert(db).values(values)
    update_cols = {
        c.name: getattr(stmt.excluded, c.name)
        for c in SpaceWeatherEvent.__table__.columns
        if c.name not in ("type", "start_time")
    }
    stmt = stmt.on_conflict_do_update(
        index_elements=["type", "start_time"], set_=update_cols
    )
    await db.execute(stmt)
    await db.commit()
    return len(values)


async def query_range(db: AsyncSession, start: datetime, end: datetime) -> list[dict]:
    """Events overlapping ``[start, end]``, newest first.

    An event overlaps the window when it begins on/before ``end`` and is either
    still ongoing (``end_time IS NULL``) or ended on/after ``start``.
    """
    stmt = (
        select(SpaceWeatherEvent)
        .where(
            SpaceWeatherEvent.start_time <= end,
            or_(
                SpaceWeatherEvent.end_time.is_(None),
                SpaceWeatherEvent.end_time >= start,
            ),
        )
        .order_by(SpaceWeatherEvent.start_time.desc())
    )
    res = await db.execute(stmt)
    return [_to_dict(o) for o in res.scalars().all()]


async def query_active_or_recent(db: AsyncSession, since: datetime) -> list[dict]:
    """Ongoing events, or those that ended on/after ``since`` — newest first.

    These are what the alert feed surfaces (current and just-subsided conditions).
    """
    stmt = (
        select(SpaceWeatherEvent)
        .where(
            or_(
                SpaceWeatherEvent.end_time.is_(None),
                SpaceWeatherEvent.end_time >= since,
            )
        )
        .order_by(SpaceWeatherEvent.start_time.desc())
    )
    res = await db.execute(stmt)
    return [_to_dict(o) for o in res.scalars().all()]
