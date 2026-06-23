"""F10.7 cm solar radio flux (sfu) — last 30 days, fetched live and Redis-cached.

A slow daily index for the overview's radio-flux panel; served live with a short
cache rather than persisted like the high-cadence time-series.
"""
from app.cache import cache_get_json, cache_set_json
from app.collectors.collect_f107 import fetch_f107_30day_json, parse_f107
from app.schemas.radio_flux_schema import F107Point, F107Response

_TTL = 3600  # 1h — the 30-day feed updates once a day.


async def get_f107_series() -> F107Response:
    key = "f107:30day"
    cached = await cache_get_json(key)
    if cached is not None:
        return F107Response.model_validate(cached)

    try:
        rows = parse_f107(await fetch_f107_30day_json())
    except Exception:
        rows = []

    resp = F107Response(data=[F107Point(time=r["time"], flux=r["flux"]) for r in rows])
    await cache_set_json(key, resp.model_dump(mode="json"), _TTL)
    return resp
