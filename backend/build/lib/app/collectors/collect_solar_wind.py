"""Fetch the latest solar-wind speed and IMF from NOAA SWPC summary feeds.

NOAA publishes single-value "summary" products tailored for dashboards:
  /products/summary/solar-wind-speed.json    -> [{"proton_speed":418,"time_tag":...}]
  /products/summary/solar-wind-mag-field.json-> [{"bt":11,"bz_gsm":6,"time_tag":...}]
Timestamps are UTC (no suffix). Each is a list with a single current reading.
"""
from datetime import datetime, timezone

import httpx

from app.config import settings


async def _fetch_summary(name: str) -> dict | None:
    url = f"{settings.noaa_base_url}/products/summary/{name}"
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.get(url)
        r.raise_for_status()
        data = r.json()
    if isinstance(data, list):
        return data[0] if data else None
    return data if isinstance(data, dict) else None


def _ts(row: dict) -> datetime | None:
    raw = row.get("time_tag")
    if not raw:
        return None
    try:
        return datetime.fromisoformat(str(raw).replace("Z", "")).replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _num(row: dict, key: str) -> float | None:
    v = row.get(key)
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


async def fetch_solar_wind_speed() -> dict | None:
    """{time, speed} for the latest plasma reading, or None if unavailable."""
    row = await _fetch_summary("solar-wind-speed.json")
    if row is None:
        return None
    return {"time": _ts(row), "speed": _num(row, "proton_speed")}


async def fetch_solar_wind_mag() -> dict | None:
    """{time, bz, bt} for the latest IMF reading, or None if unavailable."""
    row = await _fetch_summary("solar-wind-mag-field.json")
    if row is None:
        return None
    return {"time": _ts(row), "bz": _num(row, "bz_gsm"), "bt": _num(row, "bt")}
