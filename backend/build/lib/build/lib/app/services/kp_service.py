"""Kp index service — DB-backed reads with Redis cache and live fallback."""
from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.cache import cache_get_json, cache_set_json
from app.collectors.collect_kp import fetch_kp_gfz, fetch_kp_json, parse_kp
from app.models.timeseries import KpIndex
from app.processing.geomag_scale import kp_storm_scale
from app.repositories.timeseries_repo import (
    safe_query_latest,
    safe_query_range,
    safe_upsert,
)
from app.schemas.geomagnetic_schema import KpLatest, KpPoint

SOURCE = "noaa-swpc"
_LATEST_TTL = 60
_RANGE_TTL = 300
# Ranges reaching further back than this use the GFZ historical archive
# (NOAA's live feed only covers recent days).
_HISTORICAL_DAYS = 7


async def fetch_live_records() -> list[dict]:
    """Live NOAA Kp records ({time, kp}); the feed already is one row per time."""
    raw = await fetch_kp_json()
    return parse_kp(raw)


async def collect_recent_records() -> list[dict]:
    return await fetch_live_records()


async def get_kp(db: AsyncSession, start: datetime, end: datetime) -> list[KpPoint]:
    key = f"geomag:kp:range:{start.isoformat()}:{end.isoformat()}"
    cached = await cache_get_json(key)
    if cached is not None:
        return [KpPoint.model_validate(d) for d in cached]

    records = await safe_query_range(db, KpIndex, start, end)
    now = datetime.now(timezone.utc)
    if start < now - timedelta(days=_HISTORICAL_DAYS):
        # Historical range — GFZ covers the full record (the DB only holds the
        # recent NOAA ingest). Served on demand (Redis-cached), not persisted,
        # to avoid mixing GFZ + NOAA provenance under one source tag.
        try:
            live = await fetch_kp_gfz(start, end)
        except Exception:
            live = []
        if live:
            records = [r for r in live if start <= r["time"] <= end]
    elif not records:
        live = await fetch_live_records()
        await safe_upsert(db, KpIndex, live, SOURCE)
        records = [r for r in live if start <= r["time"] <= end]

    points = [
        KpPoint(time=r["time"], kp=r["kp"])
        for r in sorted(records, key=lambda r: r["time"])
    ]
    await cache_set_json(key, [p.model_dump(mode="json") for p in points], _RANGE_TTL)
    return points


async def get_kp_latest(db: AsyncSession) -> KpLatest:
    key = "geomag:kp:latest"
    cached = await cache_get_json(key)
    if cached is not None:
        return KpLatest.model_validate(cached)

    row = await safe_query_latest(db, KpIndex)
    if row is None:
        live = await fetch_live_records()
        await safe_upsert(db, KpIndex, live, SOURCE)
        row = max(live, key=lambda r: r["time"]) if live else None
    if row is None:
        return KpLatest()

    resp = KpLatest(time=row["time"], kp=row["kp"], g_scale=kp_storm_scale(row["kp"]))
    await cache_set_json(key, resp.model_dump(mode="json"), _LATEST_TTL)
    return resp
