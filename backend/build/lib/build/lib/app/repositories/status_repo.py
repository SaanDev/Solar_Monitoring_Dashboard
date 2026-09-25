"""Read/write per-source ingestion health (``source_status`` table)."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.source_status import SourceStatus


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _insert(db: AsyncSession):
    fn = sqlite_insert if db.bind.dialect.name == "sqlite" else pg_insert
    return fn(SourceStatus)


async def _upsert(db: AsyncSession, name: str, values: dict) -> None:
    now = _utcnow()
    stmt = _insert(db).values(name=name, updated_at=now, **values)
    stmt = stmt.on_conflict_do_update(
        index_elements=["name"], set_={**values, "updated_at": now}
    )
    await db.execute(stmt)
    await db.commit()


async def record_success(db: AsyncSession, name: str) -> None:
    await _upsert(db, name, {"status": "ok", "last_success_at": _utcnow(), "last_error": None})


async def record_error(db: AsyncSession, name: str, message: str) -> None:
    await _upsert(db, name, {"status": "error", "last_error": message[:500]})


async def get_all(db: AsyncSession) -> dict[str, SourceStatus]:
    res = await db.execute(select(SourceStatus))
    return {row.name: row for row in res.scalars().all()}
