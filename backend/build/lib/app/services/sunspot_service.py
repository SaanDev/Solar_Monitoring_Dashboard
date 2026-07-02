"""Sunspot number — latest daily value plus the progression series.

The latest value is a same-day EISN quick-look; the progression series backs the
dashboard chart with either a long-term monthly view (NOAA observed indices, with
the 13-month smoothed curve) or recent daily detail (SILSO daily total). All are
fetched live and Redis-cached — slow data, so nothing is persisted.
"""
from datetime import date, timedelta

from app.cache import cache_get_json, cache_set_json
from app.collectors.collect_sunspot import (
    fetch_daily_ssn_csv,
    fetch_eisn_csv,
    fetch_monthly_indices,
    latest_eisn,
    parse_daily_ssn,
    parse_eisn,
    parse_monthly_ssn,
)
from app.schemas.sunspot_schema import (
    SunspotLatest,
    SunspotSeriesPoint,
    SunspotSeriesResponse,
)

_TTL = 3600
_SERIES_TTL = 21600  # 6h — monthly/daily SSN changes at most once a day.
_RECENT_DAYS = 366    # how far back the "recent" daily view reaches.


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


async def get_sunspot_series(scope: str = "cycle") -> SunspotSeriesResponse:
    scope = "recent" if scope == "recent" else "cycle"
    key = f"sunspot:series:{scope}"
    cached = await cache_get_json(key)
    if cached is not None:
        return SunspotSeriesResponse.model_validate(cached)

    points: list[SunspotSeriesPoint] = []
    if scope == "cycle":
        source = "noaa-swpc"
        try:
            for r in parse_monthly_ssn(await fetch_monthly_indices()):
                points.append(
                    SunspotSeriesPoint(date=r["date"], number=r["ssn"], smoothed=r["smoothed_ssn"])
                )
        except Exception:
            points = []
    else:
        source = "silso-daily"
        cutoff = date.today() - timedelta(days=_RECENT_DAYS)
        try:
            for r in parse_daily_ssn(await fetch_daily_ssn_csv()):
                if r["date"] >= cutoff:
                    points.append(SunspotSeriesPoint(date=r["date"], number=r["number"]))
        except Exception:
            points = []

    resp = SunspotSeriesResponse(scope=scope, source=source, data=points)
    await cache_set_json(key, resp.model_dump(mode="json"), _SERIES_TTL)
    return resp
