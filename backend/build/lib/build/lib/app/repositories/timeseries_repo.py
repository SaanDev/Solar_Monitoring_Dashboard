"""Generic read/upsert helpers for the numeric time-series tables.

Records flow as plain dicts whose keys match the model's data columns (plus
``time``); ``source`` and ``ingested_at`` are added on write. Upserts are
idempotent on the composite key ``(time, source)`` — re-ingesting a point
updates it in place rather than duplicating it.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _dialect_name(db: AsyncSession) -> str:
    return db.bind.dialect.name


def _insert(db: AsyncSession, model: type):
    fn = sqlite_insert if _dialect_name(db) == "sqlite" else pg_insert
    return fn(model)


def _to_dict(model: type, obj) -> dict:
    return {c.name: getattr(obj, c.name) for c in model.__table__.columns}


async def upsert_points(
    db: AsyncSession, model: type, records: list[dict], source: str
) -> int:
    """Insert/update ``records`` for ``source``; returns the number written."""
    if not records:
        return 0
    now = _utcnow()
    values = [{**r, "source": source, "ingested_at": now} for r in records]
    stmt = _insert(db, model).values(values)
    update_cols = {
        c.name: getattr(stmt.excluded, c.name)
        for c in model.__table__.columns
        if c.name not in ("time", "source")
    }
    stmt = stmt.on_conflict_do_update(index_elements=["time", "source"], set_=update_cols)
    await db.execute(stmt)
    await db.commit()
    return len(values)


async def query_range(
    db: AsyncSession, model: type, start: datetime, end: datetime
) -> list[dict]:
    """Rows with ``start <= time <= end``, ascending."""
    stmt = (
        select(model)
        .where(model.time >= start, model.time <= end)
        .order_by(model.time)
    )
    res = await db.execute(stmt)
    return [_to_dict(model, o) for o in res.scalars().all()]


async def query_latest(db: AsyncSession, model: type) -> dict | None:
    """Most recent row, or ``None`` if the table is empty."""
    stmt = select(model).order_by(model.time.desc()).limit(1)
    res = await db.execute(stmt)
    obj = res.scalars().first()
    return _to_dict(model, obj) if obj else None


async def _safe_rollback(db: AsyncSession) -> None:
    try:
        await db.rollback()
    except Exception:
        pass


# ── Resilient wrappers ──────────────────────────────────────────────────────
# Services call these so a database that is empty, slow, or entirely unavailable
# degrades to a live-fetch fallback instead of erroring (the dashboard never goes
# blank). The bare ``query_*``/``upsert_*`` functions above raise as usual and are
# used where a failure should surface (ingestion, tests).


async def safe_query_range(
    db: AsyncSession, model: type, start: datetime, end: datetime
) -> list[dict]:
    try:
        return await query_range(db, model, start, end)
    except Exception as exc:
        logger.debug("range query failed for %s: %s", model.__tablename__, exc)
        await _safe_rollback(db)
        return []


async def safe_query_latest(db: AsyncSession, model: type) -> dict | None:
    try:
        return await query_latest(db, model)
    except Exception as exc:
        logger.debug("latest query failed for %s: %s", model.__tablename__, exc)
        await _safe_rollback(db)
        return None


async def safe_upsert(
    db: AsyncSession, model: type, records: list[dict], source: str
) -> int:
    try:
        return await upsert_points(db, model, records, source)
    except Exception as exc:
        logger.debug("backfill upsert failed for %s: %s", model.__tablename__, exc)
        await _safe_rollback(db)
        return 0
