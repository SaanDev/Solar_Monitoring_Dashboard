"""GOES XRS service — DB-backed reads with Redis cache and a live fallback.

Reads served from TimescaleDB (populated by the ingestion scheduler). On a cold
cache/DB miss it fetches live from NOAA, backfills the DB, and serves that — so
the dashboard works before the first scheduled ingest and if the DB is down.

NOAA channels: short = 0.05-0.4 nm (XRS-A); long = 0.1-0.8 nm (XRS-B, flare class).
"""
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.cache import cache_get_json, cache_set_json
from app.collectors.collect_goes_xrs import fetch_goes_xrs_json, records_from_raw
from app.models.timeseries import GoesXrs
from app.processing.flare_class import flare_class
from app.processing.noaa_range import pick_range_file
from app.repositories.timeseries_repo import (
    safe_query_latest,
    safe_query_range,
    safe_upsert,
)
from app.schemas.goes_schema import GoesXrsLatest, GoesXrsPoint, GoesXrsResponse

SOURCE = "noaa-swpc"
_LATEST_TTL = 30
_RANGE_TTL = 300


async def fetch_live_records(range_key: str) -> list[dict]:
    """Live NOAA records for a feed window (one dict per timestamp)."""
    raw = await fetch_goes_xrs_json(range_key)
    return records_from_raw(raw)


async def collect_recent_records() -> list[dict]:
    """Recent window used by the ingestion scheduler."""
    return await fetch_live_records("1-day")


def _point(r: dict) -> GoesXrsPoint:
    return GoesXrsPoint(
        time=r["time"], short_channel=r.get("short_channel"), long_channel=r.get("long_channel")
    )


def _satellite(records: list[dict]) -> int | None:
    return next((r.get("satellite") for r in records if r.get("satellite") is not None), None)


async def get_goes_xrs(db: AsyncSession, start: datetime, end: datetime) -> GoesXrsResponse:
    key = f"goes:xrs:range:{start.isoformat()}:{end.isoformat()}"
    cached = await cache_get_json(key)
    if cached is not None:
        return GoesXrsResponse.model_validate(cached)

    records = await safe_query_range(db, GoesXrs, start, end)
    if not records:
        live = await fetch_live_records(pick_range_file(start, end))
        await safe_upsert(db, GoesXrs, live, SOURCE)
        records = [r for r in live if start <= r["time"] <= end]

    resp = GoesXrsResponse(
        start=start, end=end, satellite=_satellite(records), data=[_point(r) for r in records]
    )
    await cache_set_json(key, resp.model_dump(mode="json"), _RANGE_TTL)
    return resp


async def get_goes_xrs_latest(db: AsyncSession) -> GoesXrsLatest:
    key = "goes:xrs:latest"
    cached = await cache_get_json(key)
    if cached is not None:
        return GoesXrsLatest.model_validate(cached)

    row = await safe_query_latest(db, GoesXrs)
    if row is None:
        live = await fetch_live_records("6-hour")
        await safe_upsert(db, GoesXrs, live, SOURCE)
        row = live[-1] if live else None
    if row is None:
        return GoesXrsLatest()

    long_flux = row.get("long_channel")
    resp = GoesXrsLatest(
        time=row["time"],
        satellite=row.get("satellite"),
        short_channel=row.get("short_channel"),
        long_channel=long_flux,
        flare_class=flare_class(long_flux),
    )
    await cache_set_json(key, resp.model_dump(mode="json"), _LATEST_TTL)
    return resp
