"""Latest solar-wind speed + IMF, fetched live from NOAA SWPC summary feeds.

These are single "current value" readings for the overview quick-look, so they are
served live with a short Redis cache rather than persisted like the time-series.
A failing feed degrades to ``None`` instead of erroring.
"""
import asyncio

from app.cache import cache_get_json, cache_set_json
from app.collectors.collect_solar_wind import fetch_solar_wind_mag, fetch_solar_wind_speed
from app.schemas.solar_wind_schema import SolarWindLatest

_TTL = 60


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
