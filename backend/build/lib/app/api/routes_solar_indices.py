"""Slow solar-activity indices: sunspot-number progression + F10.7 radio flux.

These are live-fetched and Redis-cached (no DB), backing the dashboard's
sunspot-progression chart and the F10.7 radio-flux panel.
"""
from fastapi import APIRouter, Query

from app.schemas.radio_flux_schema import F107Response
from app.schemas.sunspot_schema import SunspotSeriesResponse
from app.services.f107_service import get_f107_series
from app.services.sunspot_service import get_sunspot_series

router = APIRouter(prefix="/api/indices", tags=["indices"])


@router.get("/sunspot", response_model=SunspotSeriesResponse)
async def sunspot_series(
    scope: str = Query("cycle", pattern="^(cycle|recent)$"),
) -> SunspotSeriesResponse:
    """Sunspot-number progression: ``cycle`` = long-term monthly + 13-month
    smoothed (NOAA indices); ``recent`` = recent daily (SILSO daily total)."""
    return await get_sunspot_series(scope)


@router.get("/f107", response_model=F107Response)
async def f107_flux() -> F107Response:
    """F10.7 cm solar radio flux (sfu) — last 30 days, daily."""
    return await get_f107_series()
