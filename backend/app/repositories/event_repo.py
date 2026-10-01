"""Read/upsert helpers for the derived ``events`` table.

Upserts are idempotent on the composite key ``(type, start_time)`` — re-running
detection over an overlapping window updates an event in place (extending its
``end_time``/peak) rather than duplicating it.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import and_, delete, func, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

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
    "stations",
    "burst_type",
    "source_url",
)


# Rows per INSERT statement: a history re-derivation can upsert thousands of
# events, which in one statement would exceed the bind-parameter limits.
_UPSERT_CHUNK = 500


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
    for i in range(0, len(values), _UPSERT_CHUNK):
        stmt = _insert(db).values(values[i : i + _UPSERT_CHUNK])
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
    """Ongoing events, or those that ended on/after ``since`` — newest first."""
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


async def query_all(db: AsyncSession) -> list[dict]:
    """Every event, newest first — the full historical alert/event feed."""
    stmt = select(SpaceWeatherEvent).order_by(SpaceWeatherEvent.start_time.desc())
    res = await db.execute(stmt)
    return [_to_dict(o) for o in res.scalars().all()]


async def earliest_inconsistent_start(
    db: AsyncSession, event_type: str, open_before: datetime
) -> datetime | None:
    """Start of the earliest ``event_type`` row that a clean derivation could not
    have produced, or ``None`` if there is none.

    That is a row still open although it began before ``open_before`` (no longer
    re-derived by the rolling window, so nothing will ever close it), or one that
    overlaps a later row of the same type — a detector's spans never overlap, so
    such rows are fragments of one event stored under several starts.
    """
    ev = SpaceWeatherEvent
    stale_open = await db.scalar(
        select(func.min(ev.start_time)).where(
            ev.type == event_type, ev.end_time.is_(None), ev.start_time < open_before
        )
    )
    a, b = aliased(ev), aliased(ev)
    overlapping = await db.scalar(
        select(func.min(a.start_time))
        .join(
            b,
            and_(
                b.type == a.type,
                b.start_time > a.start_time,
                or_(a.end_time.is_(None), a.end_time >= b.start_time),
            ),
        )
        .where(a.type == event_type)
    )
    found = [_as_utc(t) for t in (stale_open, overlapping) if t is not None]
    return min(found, default=None)


def _as_utc(dt: datetime) -> datetime:
    """SQLite returns naive datetimes; treat them as UTC."""
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


async def delete_events_of_type_since(
    db: AsyncSession, event_type: str, since: datetime, keep_starts: set[datetime]
) -> int:
    """Delete events of ``event_type`` with ``start_time >= since`` whose start is
    not in ``keep_starts``. Lets a re-derivation drop events that no longer qualify
    (e.g. windows that fail the corroboration filter, or pre-filter leftovers)."""
    conds = [
        SpaceWeatherEvent.type == event_type,
        SpaceWeatherEvent.start_time >= since,
    ]
    if keep_starts:
        conds.append(SpaceWeatherEvent.start_time.not_in(list(keep_starts)))
    res = await db.execute(delete(SpaceWeatherEvent).where(*conds))
    await db.commit()
    return res.rowcount or 0


async def delete_events_of_type_in_range(
    db: AsyncSession,
    event_type: str,
    start: datetime,
    end: datetime,
    keep_starts: set[datetime],
) -> int:
    """Delete events of ``event_type`` starting in ``[start, end)`` whose start is
    not in ``keep_starts``.

    The bounded sibling of ``delete_events_of_type_since``: the offline catch-up
    re-derives one historical day at a time, so its cleanup has to stop at that
    day's edge instead of sweeping everything newer than it.
    """
    conds = [
        SpaceWeatherEvent.type == event_type,
        SpaceWeatherEvent.start_time >= start,
        SpaceWeatherEvent.start_time < end,
    ]
    if keep_starts:
        conds.append(SpaceWeatherEvent.start_time.not_in(list(keep_starts)))
    res = await db.execute(delete(SpaceWeatherEvent).where(*conds))
    await db.commit()
    return res.rowcount or 0
