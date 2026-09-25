"""Dst index service — DB-backed reads with Redis cache and live fallback.

Live source is Kyoto WDC's real-time (quicklook) Dst, so stored rows are tagged
``kyoto-wdc`` to keep their provisional provenance explicit.
"""
from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.cache import cache_get_json, cache_set_json
from app.collectors.collect_dst import fetch_dst_month, parse_dst
from app.models.timeseries import DstIndex
from app.processing.geomag_scale import dst_storm_level
from app.repositories.timeseries_repo import (
    safe_query_latest,
    safe_query_range,
    safe_upsert,
)
from app.schemas.geomagnetic_schema import DstLatest, DstPoint

SOURCE = "kyoto-wdc"
_LATEST_TTL = 60
_RANGE_TTL = 300
# Ranges reaching further back than this re-fetch from Kyoto (final/provisional
# tiers) so historical months are filled, not just the recently ingested data.
_HISTORICAL_DAYS = 7


def _months_in_range(start: datetime, end: datetime) -> list[tuple[int, int]]:
    months: list[tuple[int, int]] = []
    y, m = start.year, start.month
    while (y, m) <= (end.year, end.month):
        months.append((y, m))
        m += 1
        if m > 12:
            m, y = 1, y + 1
    return months


async def _fetch_records(start: datetime, end: datetime) -> list[dict]:
    """Live Kyoto records ({time, dst}) across the months spanning [start, end]."""
    rows: list[dict] = []
    for year, month in _months_in_range(start, end):
        try:
            text = await fetch_dst_month(year, month)
            rows.extend(parse_dst(text))
        except Exception:
            continue
    return rows


async def collect_recent_records() -> list[dict]:
    # The current month always contains the most recent hourly value.
    now = datetime.now(timezone.utc)
    return await _fetch_records(now.replace(day=1), now)


async def get_dst(db: AsyncSession, start: datetime, end: datetime) -> list[DstPoint]:
    key = f"geomag:dst:range:{start.isoformat()}:{end.isoformat()}"
    cached = await cache_get_json(key)
    if cached is not None:
        return [DstPoint.model_validate(d) for d in cached]

    records = await safe_query_range(db, DstIndex, start, end)
    now = datetime.now(timezone.utc)
    # Re-fetch from Kyoto when the range is historical (DB holds only recent
    # ingest) or when the DB has nothing for it. Dst is single-source, so the
    # fetched months are safe to persist for next time.
    if start < now - timedelta(days=_HISTORICAL_DAYS) or not records:
        live = await _fetch_records(start, end)
        if live:
            await safe_upsert(db, DstIndex, live, SOURCE)
            records = [r for r in live if start <= r["time"] <= end]

    points = [
        DstPoint(time=r["time"], dst=r["dst"])
        for r in sorted(records, key=lambda r: r["time"])
    ]
    await cache_set_json(key, [p.model_dump(mode="json") for p in points], _RANGE_TTL)
    return points


async def get_dst_latest(db: AsyncSession) -> DstLatest:
    key = "geomag:dst:latest"
    cached = await cache_get_json(key)
    if cached is not None:
        return DstLatest.model_validate(cached)

    row = await safe_query_latest(db, DstIndex)
    if row is None:
        live = await collect_recent_records()
        await safe_upsert(db, DstIndex, live, SOURCE)
        row = max(live, key=lambda r: r["time"]) if live else None
    if row is None:
        return DstLatest()

    resp = DstLatest(time=row["time"], dst=row["dst"], storm_level=dst_storm_level(row["dst"]))
    await cache_set_json(key, resp.model_dump(mode="json"), _LATEST_TTL)
    return resp
