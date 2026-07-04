"""Solar-wind speed + IMF, fetched live from NOAA SWPC feeds.

Both the single "current value" readings and the time series are served live
with a short Redis cache rather than persisted: NOAA already keeps up to seven
days of history in pre-built windows. A failing feed degrades to ``None`` /
empty instead of erroring.
"""
import asyncio
from datetime import datetime, timedelta, timezone

from app.cache import cache_get_json, cache_set_json
from app.collectors.collect_solar_wind import (
    fetch_solar_wind_mag,
    fetch_solar_wind_series,
    fetch_solar_wind_speed,
)
from app.schemas.solar_wind_schema import SolarWindLatest, SolarWindSeries

_TTL = 60

# UI range keys -> window width. All are sliced from the one 7-day NOAA feed.
SERIES_RANGES: dict[str, int] = {
    "2-hour": 2,
    "6-hour": 6,
    "1-day": 24,
    "3-day": 72,
    "7-day": 168,
}


async def get_solar_wind_latest() -> SolarWindLatest:
    key = "summary:solar-wind"
    cached = await cache_get_json(key)
    if cached is not None:
        return SolarWindLatest.model_validate(cached)

    speed_row, mag_row = await asyncio.gather(
        fetch_solar_wind_speed(), fetch_solar_wind_mag(), return_exceptions=True
    )
    speed = speed_row if isinstance(speed_row, dict) else {}
    mag = mag_row if isinstance(mag_row, dict) else {}

    resp = SolarWindLatest(
        time=mag.get("time") or speed.get("time"),
        speed=speed.get("speed"),
        bz=mag.get("bz"),
        bt=mag.get("bt"),
    )
    await cache_set_json(key, resp.model_dump(mode="json"), _TTL)
    return resp


async def _full_series() -> SolarWindSeries:
    """The whole 7-day feed, parsed once per TTL and shared by every range."""
    key = "solar-wind:series:full"
    cached = await cache_get_json(key)
    if cached is not None:
        return SolarWindSeries.model_validate(cached)

    try:
        points = await fetch_solar_wind_series()
    except Exception:
        points = []
    resp = SolarWindSeries(range="7-day", data=points)
    # Don't cache an outage: the next request should retry NOAA right away.
    if resp.data:
        await cache_set_json(key, resp.model_dump(mode="json"), _TTL)
    return resp


async def get_solar_wind_series(range_key: str) -> SolarWindSeries:
    full = await _full_series()
    hours = SERIES_RANGES.get(range_key, 168)
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    return SolarWindSeries(
        range=range_key,
        data=[p for p in full.data if p.time >= cutoff],
    )
