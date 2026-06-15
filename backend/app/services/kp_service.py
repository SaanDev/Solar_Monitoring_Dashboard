"""Kp index service — live NOAA planetary K-index."""
from datetime import datetime

from app.collectors.collect_kp import fetch_kp_json, parse_kp
from app.processing.geomag_scale import kp_storm_scale
from app.schemas.geomagnetic_schema import KpPoint, KpLatest


async def get_kp(start: datetime, end: datetime) -> list[KpPoint]:
    raw = await fetch_kp_json()
    rows = parse_kp(raw)
    return [
        KpPoint(time=r["time"], kp=r["kp"])
        for r in rows
        if start <= r["time"] <= end
    ]


async def get_kp_latest() -> KpLatest:
    raw = await fetch_kp_json()
    rows = parse_kp(raw)
    if not rows:
        return KpLatest()
    last = max(rows, key=lambda r: r["time"])
    return KpLatest(time=last["time"], kp=last["kp"], g_scale=kp_storm_scale(last["kp"]))
