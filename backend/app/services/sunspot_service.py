"""Latest daily sunspot number, fetched live from SILSO (EISN), Redis-cached.

A daily value for the overview quick-look — refreshed hourly, not persisted.
"""
from app.cache import cache_get_json, cache_set_json
from app.collectors.collect_sunspot import fetch_eisn_csv, latest_eisn, parse_eisn
from app.schemas.sunspot_schema import SunspotLatest

_TTL = 3600


async def get_sunspot_latest() -> SunspotLatest:
    key = "summary:sunspot"
    cached = await cache_get_json(key)
    if cached is not None:
        return SunspotLatest.model_validate(cached)

    try:
        row = latest_eisn(parse_eisn(await fetch_eisn_csv()))
    except Exception:
        row = None

    resp = SunspotLatest(
        date=row["date"] if row else None,
        number=row["number"] if row else None,
    )
    await cache_set_json(key, resp.model_dump(mode="json"), _TTL)
    return resp
