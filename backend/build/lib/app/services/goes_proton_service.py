"""GOES proton flux service — DB-backed reads with Redis cache and live fallback.

Integral fluxes >=10 / >=50 / >=100 MeV (particles / cm^2 s sr). Reads come from
TimescaleDB; a cold miss falls back to live NOAA and backfills.
"""
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.cache import cache_get_json, cache_set_json
from app.collectors.collect_goes_proton import fetch_goes_proton_json, records_from_raw
from app.models.timeseries import GoesProton
from app.processing.noaa_range import pick_range_file
from app.processing.storm_scale import PROTON_EVENT_THRESHOLD_PFU, storm_scale
from app.repositories.timeseries_repo import (
    safe_query_latest,
    safe_query_range,
    safe_upsert,
)
from app.schemas.goes_schema import GoesProtonLatest, GoesProtonPoint, GoesProtonResponse

SOURCE = "noaa-swpc"
_LATEST_TTL = 30
_RANGE_TTL = 300


async def fetch_live_records(range_key: str) -> list[dict]:
    raw = await fetch_goes_proton_json(range_key)
    return records_from_raw(raw)


async def collect_recent_records() -> list[dict]:
    return await fetch_live_records("1-day")


def _point(r: dict) -> GoesProtonPoint:
    return GoesProtonPoint(
        time=r["time"],
        flux_gt10=r.get("flux_gt10"),
        flux_gt50=r.get("flux_gt50"),
        flux_gt100=r.get("flux_gt100"),
    )


def _satellite(records: list[dict]) -> int | None:
    return next((r.get("satellite") for r in records if r.get("satellite") is not None), None)


async def get_goes_proton(db: AsyncSession, start: datetime, end: datetime) -> GoesProtonResponse:
    key = f"goes:proton:range:{start.isoformat()}:{end.isoformat()}"
    cached = await cache_get_json(key)
    if cached is not None:
        return GoesProtonResponse.model_validate(cached)

    records = await safe_query_range(db, GoesProton, start, end)
    if not records:
        live = await fetch_live_records(pick_range_file(start, end))
        await safe_upsert(db, GoesProton, live, SOURCE)
        records = [r for r in live if start <= r["time"] <= end]

    resp = GoesProtonResponse(
        start=start, end=end, satellite=_satellite(records), data=[_point(r) for r in records]
    )
    await cache_set_json(key, resp.model_dump(mode="json"), _RANGE_TTL)
    return resp


async def get_goes_proton_latest(db: AsyncSession) -> GoesProtonLatest:
    key = "goes:proton:latest"
    cached = await cache_get_json(key)
    if cached is not None:
        return GoesProtonLatest.model_validate(cached)

    row = await safe_query_latest(db, GoesProton)
    if row is None:
        live = await fetch_live_records("6-hour")
        await safe_upsert(db, GoesProton, live, SOURCE)
        row = live[-1] if live else None
    if row is None:
        return GoesProtonLatest()

    flux10 = row.get("flux_gt10")
    resp = GoesProtonLatest(
        time=row["time"],
        satellite=row.get("satellite"),
        flux_gt10=flux10,
        flux_gt50=row.get("flux_gt50"),
        flux_gt100=row.get("flux_gt100"),
        storm_scale=storm_scale(flux10),
        event_in_progress=flux10 is not None and flux10 >= PROTON_EVENT_THRESHOLD_PFU,
    )
    await cache_set_json(key, resp.model_dump(mode="json"), _LATEST_TTL)
    return resp
