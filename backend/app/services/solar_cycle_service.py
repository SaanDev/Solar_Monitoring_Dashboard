"""Solar-cycle progression, live-proxied from NOAA with a long Redis cache
(monthly products — 6 h freshness is generous). Observed history starts at
Cycle 24's opening minimum so the previous cycle gives visual context."""
from __future__ import annotations

import logging

from app.cache import cache_get_json, cache_set_json
from app.collectors.collect_solar_cycle import fetch_observed, fetch_predicted
from app.schemas.solar_cycle_schema import SolarCycleResponse

logger = logging.getLogger(__name__)

_TTL = 6 * 3600
# Cycle 24 began 2008-12; showing it alongside Cycle 25 makes the "weak vs
# strong cycle" comparison the page exists for.
_OBSERVED_SINCE = "2008-12"


async def get_solar_cycle() -> SolarCycleResponse:
    key = "indices:solar-cycle"
    cached = await cache_get_json(key)
    if cached is not None:
        return SolarCycleResponse.model_validate(cached)

    try:
        observed = await fetch_observed(_OBSERVED_SINCE)
    except Exception as exc:  # noqa: BLE001 - degrade to empty
        logger.warning("observed solar-cycle fetch failed: %s", exc)
        observed = []
    try:
        predicted = await fetch_predicted()
    except Exception as exc:  # noqa: BLE001
        logger.warning("predicted solar-cycle fetch failed: %s", exc)
        predicted = []

    resp = SolarCycleResponse(observed=observed, predicted=predicted)
    if resp.observed or resp.predicted:
        await cache_set_json(key, resp.model_dump(mode="json"), _TTL)
    return resp
