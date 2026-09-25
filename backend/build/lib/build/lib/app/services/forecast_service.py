"""Forecast reads + predicted-storm detection.

Three products, all derived/proxied live with a short Redis cache (NOAA keeps
the history; nothing here needs the DB except the predicted-storm events):

* Predicted Kp — the Newell coupling / Kp regression computed over NOAA's
  propagated L1 solar wind (see ``app.processing.kp_prediction``). The full
  7-day series is computed once per TTL and sliced per UI range, mirroring
  the solar-wind service.
* NOAA 3-day R/S/G outlook — normalized noaa-scales.json.
* OVATION aurora — hemispheric power + NOAA's rendered oval images.

A scheduled detection pass segments the smoothed predicted-Kp series into
``geomagnetic_storm_prediction`` events (G1 onset and up) so a coupling episode
reaches the alert feed *before* the measured Kp confirms the storm.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.cache import cache_get_json, cache_set_json
from app.collectors.collect_noaa_forecast import fetch_hemi_power, fetch_noaa_scales
from app.collectors.collect_solar_wind import fetch_coupling_series
from app.config import settings
from app.processing.geomag_scale import kp_storm_scale
from app.processing.kp_prediction import (
    predict_series,
    predicted_storm_events,
    smooth_series,
)
from app.repositories.event_repo import delete_events_of_type_since, upsert_events
from app.schemas.forecast_schema import (
    AuroraForecast,
    KpForecastLatest,
    KpForecastPoint,
    KpForecastResponse,
    NoaaScalesResponse,
)
from app.services.solar_wind_service import SERIES_RANGES

logger = logging.getLogger(__name__)

_KP_TTL = 60
_SCALES_TTL = 600
_AURORA_TTL = 300

# How far back the predicted-storm detection re-derives events (mirrors the
# real detectors' lookback so an episode keeps updating across passes).
PREDICTION_LOOKBACK_DAYS = 3

# The 1-minute series is decimated to this step for the API payload (the
# trailing-hour smoothing leaves nothing meaningful between 5-min samples).
_DECIMATE_MINUTES = 5


# ── Predicted Kp ─────────────────────────────────────────────────────────────


async def _smoothed_prediction() -> list[dict]:
    """Trailing-hour-smoothed ``[{time, kp, coupling}]`` over the full feed."""
    points = await fetch_coupling_series()
    return smooth_series(predict_series(points))


async def _full_kp_forecast() -> KpForecastResponse:
    """The whole 7-day predicted-Kp series, computed once per TTL."""
    key = "forecast:kp:full"
    cached = await cache_get_json(key)
    if cached is not None:
        return KpForecastResponse.model_validate(cached)

    try:
        smoothed = await _smoothed_prediction()
    except Exception as exc:  # noqa: BLE001 - degrade to empty, like solar wind
        logger.warning("Kp forecast computation failed: %s", exc)
        smoothed = []

    data = [
        KpForecastPoint(time=p["time"], kp=p["kp"])
        for p in smoothed
        if p["time"].minute % _DECIMATE_MINUTES == 0
    ]
    latest = KpForecastLatest()
    valid = [p for p in smoothed if p["kp"] is not None]
    if valid:
        last = valid[-1]
        latest = KpForecastLatest(
            time=last["time"],
            kp=last["kp"],
            coupling=last["coupling"],
            g_scale=kp_storm_scale(last["kp"]),
        )

    resp = KpForecastResponse(range="7-day", latest=latest, data=data)
    # Don't cache an outage: the next request should retry NOAA right away.
    if resp.data:
        await cache_set_json(key, resp.model_dump(mode="json"), _KP_TTL)
    return resp


async def get_kp_forecast(range_key: str) -> KpForecastResponse:
    full = await _full_kp_forecast()
    hours = SERIES_RANGES.get(range_key, 24)
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    return KpForecastResponse(
        range=range_key,
        latest=full.latest,
        data=[p for p in full.data if p.time >= cutoff],
    )


async def detect_and_store_predicted_storms(db: AsyncSession) -> int:
    """Segment the smoothed prediction into events and upsert them. Never raises.

    Re-derivation is authoritative for the lookback window (an episode that no
    longer reaches the G1 onset after a data revision is deleted); a failed
    feed read reconciles nothing so a transient outage can't wipe history.
    """
    start = datetime.now(timezone.utc) - timedelta(days=PREDICTION_LOOKBACK_DAYS)
    try:
        smoothed = await _smoothed_prediction()
        samples = [(p["time"], p["kp"]) for p in smoothed if p["time"] >= start]
        events = predicted_storm_events(samples)
        if samples:
            await delete_events_of_type_since(
                db,
                "geomagnetic_storm_prediction",
                start,
                {e["start_time"] for e in events},
            )
        count = await upsert_events(db, events, source="forecast")
        if count:
            logger.info("predicted-storm pass stored %d events", count)
        return count
    except Exception as exc:  # noqa: BLE001 - defensive, mirrors event detection
        await db.rollback()
        logger.warning("predicted-storm detection failed: %s", exc)
        return 0


# ── NOAA 3-day outlook ───────────────────────────────────────────────────────


async def get_noaa_scales() -> NoaaScalesResponse:
    key = "forecast:noaa-scales"
    cached = await cache_get_json(key)
    if cached is not None:
        return NoaaScalesResponse.model_validate(cached)

    try:
        parsed = await fetch_noaa_scales()
    except Exception as exc:  # noqa: BLE001
        logger.warning("noaa-scales fetch failed: %s", exc)
        return NoaaScalesResponse()
    resp = NoaaScalesResponse.model_validate(parsed)
    await cache_set_json(key, resp.model_dump(mode="json"), _SCALES_TTL)
    return resp


# ── OVATION aurora ───────────────────────────────────────────────────────────


async def get_aurora() -> AuroraForecast:
    key = "forecast:aurora"
    cached = await cache_get_json(key)
    if cached is not None:
        return AuroraForecast.model_validate(cached)

    power = None
    try:
        power = await fetch_hemi_power()
    except Exception as exc:  # noqa: BLE001 - images still render without power
        logger.warning("hemispheric power fetch failed: %s", exc)

    resp = AuroraForecast(
        observation_time=(power or {}).get("observation_time"),
        forecast_time=(power or {}).get("forecast_time"),
        power_north_gw=(power or {}).get("north_gw"),
        power_south_gw=(power or {}).get("south_gw"),
        # NOAA re-renders these every ~5 minutes; hotlinking keeps us off the
        # 1-2 MB OVATION grid JSON while still showing the official product.
        north_image_url=f"{settings.noaa_base_url}/images/animations/ovation/north/latest.jpg",
        south_image_url=f"{settings.noaa_base_url}/images/animations/ovation/south/latest.jpg",
    )
    await cache_set_json(key, resp.model_dump(mode="json"), _AURORA_TTL)
    return resp
