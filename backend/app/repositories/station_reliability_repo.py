"""Read/write helpers for ``radio_station_reliability`` (one row per station)."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.station_reliability import OVERRIDE_AUTO, StationReliability

# Columns a recomputation rewrites; ``override`` is deliberately not among them.
_MEASURED = (
    "model_id",
    "files",
    "bursts",
    "judged",
    "confirmed",
    "chance_rate",
    "score",
    "duty",
    "observed_minutes",
    "null_counts",
    "anchor_counts",
    "computed_at",
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def to_dict(row: StationReliability) -> dict:
    return {c.name: getattr(row, c.name) for c in StationReliability.__table__.columns}


async def all_rows(db: AsyncSession) -> dict[str, dict]:
    res = await db.execute(select(StationReliability))
    return {r.station: to_dict(r) for r in res.scalars().all()}


_UNMEASURED = {
    "files": 0,
    "bursts": 0,
    "judged": 0,
    "confirmed": 0,
    "chance_rate": None,
    "score": None,
    "duty": None,
    "observed_minutes": 0,
    "null_counts": None,
    "anchor_counts": None,
}


async def save_measurements(
    db: AsyncSession, measured: dict[str, dict], model_id: str, computed_at: datetime
) -> None:
    """Replace every station's measured columns, keeping overrides.

    A station that has a row but was not measured this time (no sun-up data in
    the window) has its measurement reset, so a stale score cannot outlive the
    data it came from.
    """
    res = await db.execute(select(StationReliability))
    rows = {r.station: r for r in res.scalars().all()}
    for station in set(rows) | set(measured):
        row = rows.get(station)
        if row is None:
            row = StationReliability(station=station, override=OVERRIDE_AUTO)
            db.add(row)
        values = {**_UNMEASURED, **measured.get(station, {}),
                  "model_id": model_id, "computed_at": computed_at}
        for col in _MEASURED:
            setattr(row, col, values[col])
        row.updated_at = computed_at
    await db.commit()


async def set_override(db: AsyncSession, station: str, override: str) -> dict:
    row = await db.get(StationReliability, station)
    if row is None:
        row = StationReliability(station=station)
        db.add(row)
    row.override = override
    row.updated_at = _utcnow()
    await db.commit()
    await db.refresh(row)
    return to_dict(row)
