"""Forecasting & prediction: predicted Kp (Newell coupling over L1 solar wind),
the DONKI CME catalog with WSA-ENLIL Earth-arrival predictions, NOAA's 3-day
R/S/G outlook, and the OVATION aurora forecast."""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas.forecast_schema import (
    AuroraForecast,
    CmeListResponse,
    KpForecastResponse,
    NoaaScalesResponse,
)
from app.services.cme_service import get_cmes
from app.services.forecast_service import get_aurora, get_kp_forecast, get_noaa_scales

router = APIRouter(prefix="/api/forecast", tags=["forecast"])


@router.get("/kp", response_model=KpForecastResponse)
async def kp_forecast(
    range: str = Query("1-day", pattern="^(2-hour|6-hour|1-day|3-day|7-day)$"),
) -> KpForecastResponse:
    """Predicted Kp from real-time solar-wind coupling (trailing-hour smoothed)."""
    return await get_kp_forecast(range)


@router.get("/cmes", response_model=CmeListResponse)
async def cmes(
    days: int = Query(7, ge=1, le=30),
    db: AsyncSession = Depends(get_db),
) -> CmeListResponse:
    """Recent CMEs from the DONKI catalog, newest first."""
    return await get_cmes(db, days)


@router.get("/noaa-scales", response_model=NoaaScalesResponse)
async def noaa_scales() -> NoaaScalesResponse:
    """NOAA's R/S/G scales: yesterday, today so far, and the 3-day forecast."""
    return await get_noaa_scales()


@router.get("/aurora", response_model=AuroraForecast)
async def aurora() -> AuroraForecast:
    """OVATION aurora forecast: hemispheric power + rendered oval images."""
    return await get_aurora()
