"""Read/upsert helpers for the ``radio_burst_detections`` table.

Upserts are idempotent on the primary key ``filename`` so a re-scan of the same
archive file updates its row in place rather than duplicating it. The same table
backs both dedup (``processed_filenames_since``) and event aggregation
(``burst_positive_in_range``).
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import and_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.radio_detections import RadioBurstDetection

logger = logging.getLogger(__name__)

_FIELDS = (
    "filename",
    "station",
    "start_time",
    "end_time",
    "focus",
    "probability",
    "predicted_label",
    "alert_level",
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _insert(db: AsyncSession):
    fn = sqlite_insert if db.bind.dialect.name == "sqlite" else pg_insert
    return fn(RadioBurstDetection)


def _to_dict(obj: RadioBurstDetection) -> dict:
    return {c.name: getattr(obj, c.name) for c in RadioBurstDetection.__table__.columns}


async def upsert_detections(db: AsyncSession, rows: list[dict]) -> int:
    """Insert/update scored-file rows; returns the number written."""
    if not rows:
        return 0
    now = _utcnow()
    values = [
        {**{f: r.get(f) for f in _FIELDS}, "processed_at": now} for r in rows
    ]
    stmt = _insert(db).values(values)
    update_cols = {
        c.name: getattr(stmt.excluded, c.name)
        for c in RadioBurstDetection.__table__.columns
        if c.name != "filename"
    }
    stmt = stmt.on_conflict_do_update(index_elements=["filename"], set_=update_cols)
    await db.execute(stmt)
    await db.commit()
    return len(values)


async def processed_filenames_since(db: AsyncSession, since: datetime) -> set[str]:
    """Filenames already scored whose segment starts on/after ``since`` — the
    dedup set the scanner checks before downloading anything."""
    stmt = select(RadioBurstDetection.filename).where(
        RadioBurstDetection.start_time >= since
    )
    res = await db.execute(stmt)
    return {row[0] for row in res.all()}


async def detections_for_range(
    db: AsyncSession, start: datetime, end: datetime
) -> list[dict]:
    """All scored files with segment start in ``[start, end)``, newest first —
    backs the per-file inspection endpoint."""
    stmt = (
        select(RadioBurstDetection)
        .where(
            and_(
                RadioBurstDetection.start_time >= start,
                RadioBurstDetection.start_time < end,
            )
        )
        .order_by(RadioBurstDetection.start_time.desc())
    )
    res = await db.execute(stmt)
    return [_to_dict(o) for o in res.scalars().all()]


async def burst_positive_in_range(
    db: AsyncSession, start: datetime, end: datetime, min_probability: float
) -> list[dict]:
    """Burst-positive detections with segment start in ``[start, end]`` and
    probability ``>= min_probability`` — the input to event aggregation."""
    stmt = (
        select(RadioBurstDetection)
        .where(
            and_(
                RadioBurstDetection.start_time >= start,
                RadioBurstDetection.start_time <= end,
                RadioBurstDetection.predicted_label == "Burst",
                RadioBurstDetection.probability >= min_probability,
            )
        )
        .order_by(RadioBurstDetection.start_time.asc())
    )
    res = await db.execute(stmt)
    return [_to_dict(o) for o in res.scalars().all()]
