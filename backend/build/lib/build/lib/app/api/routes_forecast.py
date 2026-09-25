"""Forecasting & prediction: predicted Kp (Newell coupling over L1 solar wind),
the DONKI CME catalog with WSA-ENLIL Earth-arrival predictions, NOAA's 3-day
R/S/G outlook, and the OVATION aurora forecast."""
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas.forecast_schema import (
    AuroraForecast,
    CmeHistogramResponse,
    CmeHistoryResponse,
    CmeListResponse,
    KpForecastResponse,
    NoaaScalesResponse,
)
from app.services.cme_service import get_cme_histogram, get_cmes, get_cmes_range
from app.services.forecast_service import get_aurora, get_kp_forecast, get_noaa_scales

# Guard the on-demand DONKI history window so one request can't ask for years.
_MAX_HISTORY_DAYS = 366


def _validate_window(start: date, end: date) -> None:
    """Reject an unordered or over-long CME history/histogram window."""
    if end < start:
        raise HTTPException(status_code=422, detail="end must be on or after start")
    if end - start > timedelta(days=_MAX_HISTORY_DAYS):
        raise HTTPException(
            status_code=422, detail=f"window exceeds {_MAX_HISTORY_DAYS} days"
        )

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


@router.get("/cmes/history", response_model=CmeHistoryResponse)
async def cmes_history(
    start: date = Query(..., description="Window start (UTC date, inclusive)"),
    end: date = Query(..., description="Window end (UTC date, inclusive)"),
    db: AsyncSession = Depends(get_db),
) -> CmeHistoryResponse:
    """Past CMEs over an arbitrary date window, newest first.

    Windows older than the retained rolling catalog are fetched on demand from
    DONKI. The span is capped and dates must be ordered.
    """
    _validate_window(start, end)
    return await get_cmes_range(db, start, end)


@router.get("/cmes/histogram", response_model=CmeHistogramResponse)
async def cmes_histogram(
    start: date = Query(..., description="Period start (UTC date, inclusive)"),
    end: date = Query(..., description="Period end (UTC date, inclusive)"),
    interval: int = Query(1, ge=1, le=30, description="Bin width in days"),
    db: AsyncSession = Depends(get_db),
) -> CmeHistogramResponse:
    """CME counts per ``interval``-day bin over the period (bins oldest first).

    Backs the per-day CME histogram; old periods are fetched on demand.
    """
    _validate_window(start, end)
    return await get_cme_histogram(db, start, end, interval)


@router.get("/noaa-scales", response_model=NoaaScalesResponse)
async def noaa_scales() -> NoaaScalesResponse:
    """NOAA's R/S/G scales: yesterday, today so far, and the 3-day forecast."""
    return await get_noaa_scales()


@router.get("/aurora", response_model=AuroraForecast)
async def aurora() -> AuroraForecast:
    """OVATION aurora forecast: hemispheric power + rendered oval images."""
    return await get_aurora()
