"""Read/upsert helpers for the ``radio_burst_detections`` table.

Upserts are idempotent on the primary key ``filename`` so a re-scan of the same
archive file updates its row in place rather than duplicating it — including when
the re-scan used a different model, which is how switching
``radio_burst_binary_model`` refreshes the recent window. The same table backs
both dedup (``processed_filenames_since``) and event aggregation
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
    "model_id",
    "burst_type",
    "type_confidence",
    "type_model_id",
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _insert(db: AsyncSession):
    fn = sqlite_insert if db.bind.dialect.name == "sqlite" else pg_insert
    return fn(RadioBurstDetection)


def _to_dict(obj: RadioBurstDetection) -> dict:
    return {c.name: getattr(obj, c.name) for c in RadioBurstDetection.__table__.columns}


async def upsert_detections(db: AsyncSession, rows: list[dict]) -> int:
    """Insert/update scored-file rows; returns the number written.

    ``model_id`` is NOT NULL, and passing an explicit None would override the
    column's server default, so a row that arrives without one is attributed to
    the configured model. In practice inference always sets it — this only covers
    callers that predate model selection.
    """
    if not rows:
        return 0
    from app.ml.registry import resolve_binary

    now = _utcnow()
    default_model = resolve_binary().id
    values = [
        {
            **{f: r.get(f) for f in _FIELDS},
            "model_id": r.get("model_id") or default_model,
            "processed_at": now,
        }
        for r in rows
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


async def processed_filenames_since(
    db: AsyncSession, since: datetime, model_id: str | None = None
) -> set[str]:
    """Filenames already scored whose segment starts on/after ``since`` — the
    dedup set the scanner checks before downloading anything.

    Scoped to ``model_id`` when given, so switching the configured scan model
    re-scores the recent window with the new model instead of skipping every file
    as "already processed" and leaving the old model's verdicts in place.
    """
    stmt = select(RadioBurstDetection.filename).where(
        RadioBurstDetection.start_time >= since
    )
    if model_id:
        stmt = stmt.where(RadioBurstDetection.model_id == model_id)
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
