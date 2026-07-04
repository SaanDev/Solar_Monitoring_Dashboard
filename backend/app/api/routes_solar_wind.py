"""Real-time solar wind: speed + IMF Bt/Bz, live-proxied from NOAA SWPC.

Series are sliced from NOAA's propagated-solar-wind feed (7 days @ 1 min),
Redis-cached for a minute — no DB persistence (NOAA keeps the history for us).
"""
from fastapi import APIRouter, Query

from app.schemas.solar_wind_schema import SolarWindLatest, SolarWindSeries
from app.services.solar_wind_service import get_solar_wind_latest, get_solar_wind_series

router = APIRouter(prefix="/api/solar-wind", tags=["solar-wind"])


@router.get("/latest", response_model=SolarWindLatest)
async def solar_wind_latest() -> SolarWindLatest:
    """Current solar-wind speed + IMF reading (NOAA summary feeds)."""
    return await get_solar_wind_latest()


@router.get("/series", response_model=SolarWindSeries)
async def solar_wind_series(
    range: str = Query("1-day", pattern="^(2-hour|6-hour|1-day|3-day|7-day)$"),
) -> SolarWindSeries:
    """Solar-wind speed and IMF Bt/Bz time series over the requested window."""
    return await get_solar_wind_series(range)
