"""Dst index service — live Kyoto WDC real-time hourly Dst."""
from datetime import datetime

from app.collectors.collect_dst import fetch_dst_month, parse_dst
from app.processing.geomag_scale import dst_storm_level
from app.schemas.geomagnetic_schema import DstPoint, DstLatest


def _months_in_range(start: datetime, end: datetime) -> list[tuple[int, int]]:
    months: list[tuple[int, int]] = []
    y, m = start.year, start.month
    while (y, m) <= (end.year, end.month):
        months.append((y, m))
        m += 1
        if m > 12:
            m, y = 1, y + 1
    return months


async def _fetch_rows(start: datetime, end: datetime) -> list[dict]:
    rows: list[dict] = []
    for year, month in _months_in_range(start, end):
        try:
            text = await fetch_dst_month(year, month)
            rows.extend(parse_dst(text))
        except Exception:
            continue
    return rows


async def get_dst(start: datetime, end: datetime) -> list[DstPoint]:
    rows = await _fetch_rows(start, end)
    return [
        DstPoint(time=r["time"], dst=r["dst"])
        for r in sorted(rows, key=lambda r: r["time"])
        if start <= r["time"] <= end
    ]


async def get_dst_latest() -> DstLatest:
    # The present month always contains the most recent hourly value.
    now = datetime.utcnow()
    rows = await _fetch_rows(now.replace(day=1), now)
    if not rows:
        return DstLatest()
    last = max(rows, key=lambda r: r["time"])
    return DstLatest(
        time=last["time"], dst=last["dst"], storm_level=dst_storm_level(last["dst"])
    )
