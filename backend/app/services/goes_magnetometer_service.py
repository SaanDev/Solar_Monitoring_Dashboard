"""GOES magnetometer service — DB-backed reads with Redis cache and live fallback.

Geomagnetic field components at the satellite (nT): Hp / He / Hn + total field.
Reads come from TimescaleDB; a cold miss falls back to live NOAA and backfills.
"""
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.cache import cache_get_json, cache_set_json
from app.collectors.collect_goes_magnetometer import (
    fetch_goes_magnetometer_json,
    records_from_raw,
)
from app.models.timeseries import GoesMagnetometer
from app.processing.noaa_range import pick_range_file
from app.repositories.timeseries_repo import (
    safe_query_latest,
    safe_query_range,
    safe_upsert,
)
from app.schemas.goes_schema import (
    GoesMagnetometerLatest,
    GoesMagnetometerPoint,
    GoesMagnetometerResponse,
)

SOURCE = "noaa-swpc"
_LATEST_TTL = 30
_RANGE_TTL = 300


async def fetch_live_records(range_key: str) -> list[dict]:
    raw = await fetch_goes_magnetometer_json(range_key)
    return records_from_raw(raw)


async def collect_recent_records() -> list[dict]:
    return await fetch_live_records("1-day")


def _point(r: dict) -> GoesMagnetometerPoint:
    return GoesMagnetometerPoint(
        time=r["time"],
        hp=r.get("hp"),
        he=r.get("he"),
        hn=r.get("hn"),
        total=r.get("total"),
    )


def _satellite(records: list[dict]) -> int | None:
    return next((r.get("satellite") for r in records if r.get("satellite") is not None), None)


async def get_goes_magnetometer(
    db: AsyncSession, start: datetime, end: datetime
) -> GoesMagnetometerResponse:
    key = f"goes:magnetometer:range:{start.isoformat()}:{end.isoformat()}"
    cached = await cache_get_json(key)
    if cached is not None:
        return GoesMagnetometerResponse.model_validate(cached)

    records = await safe_query_range(db, GoesMagnetometer, start, end)
    if not records:
        live = await fetch_live_records(pick_range_file(start, end))
        await safe_upsert(db, GoesMagnetometer, live, SOURCE)
        records = [r for r in live if start <= r["time"] <= end]

    resp = GoesMagnetometerResponse(
        start=start, end=end, satellite=_satellite(records), data=[_point(r) for r in records]
    )
    await cache_set_json(key, resp.model_dump(mode="json"), _RANGE_TTL)
    return resp


async def get_goes_magnetometer_latest(db: AsyncSession) -> GoesMagnetometerLatest:
    key = "goes:magnetometer:latest"
    cached = await cache_get_json(key)
    if cached is not None:
        return GoesMagnetometerLatest.model_validate(cached)

    row = await safe_query_latest(db, GoesMagnetometer)
    if row is None:
        live = await fetch_live_records("6-hour")
        await safe_upsert(db, GoesMagnetometer, live, SOURCE)
        row = live[-1] if live else None
    if row is None:
        return GoesMagnetometerLatest()

    resp = GoesMagnetometerLatest(
        time=row["time"],
        satellite=row.get("satellite"),
        hp=row.get("hp"),
        he=row.get("he"),
        hn=row.get("hn"),
        total=row.get("total"),
    )
    await cache_set_json(key, resp.model_dump(mode="json"), _LATEST_TTL)
    return resp
