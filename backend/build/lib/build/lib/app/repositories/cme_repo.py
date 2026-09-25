"""Read/upsert helpers for the DONKI CME catalog (``cme_events`` table).

Upserts are idempotent on ``activity_id``: DONKI analysts revise a CME's
cone-model fit and ENLIL runs for days after the eruption, so re-ingesting a
window must update rows in place, never duplicate them.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.cme import CmeEvent

# Columns written from a parsed DONKI record; updated_at is set here.
_CME_FIELDS = (
    "activity_id",
    "start_time",
    "source_location",
    "active_region",
    "latitude",
    "longitude",
    "half_angle",
    "speed",
    "cme_type",
    "time21_5",
    "is_earth_directed",
    "predicted_arrival_time",
    "predicted_kp",
    "note",
    "catalog_link",
)


def _insert(db: AsyncSession):
    fn = sqlite_insert if db.bind.dialect.name == "sqlite" else pg_insert
    return fn(CmeEvent)


def _to_dict(obj: CmeEvent) -> dict:
    return {c.name: getattr(obj, c.name) for c in CmeEvent.__table__.columns}


async def upsert_cmes(db: AsyncSession, records: list[dict]) -> int:
    if not records:
        return 0
    now = datetime.now(timezone.utc)
    values = [
        {**{f: r.get(f) for f in _CME_FIELDS}, "updated_at": now} for r in records
    ]
    stmt = _insert(db).values(values)
    update_cols = {
        c.name: getattr(stmt.excluded, c.name)
        for c in CmeEvent.__table__.columns
        if c.name != "activity_id"
    }
    stmt = stmt.on_conflict_do_update(index_elements=["activity_id"], set_=update_cols)
    await db.execute(stmt)
    await db.commit()
    return len(values)


async def query_since(db: AsyncSession, since: datetime) -> list[dict]:
    """CMEs first observed at/after ``since``, newest first."""
    stmt = (
        select(CmeEvent)
        .where(CmeEvent.start_time >= since)
        .order_by(CmeEvent.start_time.desc())
    )
    res = await db.execute(stmt)
    return [_to_dict(o) for o in res.scalars().all()]


async def query_between(
    db: AsyncSession, start: datetime, end: datetime
) -> list[dict]:
    """CMEs first observed in ``[start, end]`` (inclusive), newest first."""
    stmt = (
        select(CmeEvent)
        .where(CmeEvent.start_time >= start, CmeEvent.start_time <= end)
        .order_by(CmeEvent.start_time.desc())
    )
    res = await db.execute(stmt)
    return [_to_dict(o) for o in res.scalars().all()]
