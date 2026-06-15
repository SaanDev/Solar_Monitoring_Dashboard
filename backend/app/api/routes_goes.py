from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Query, HTTPException

from app.schemas.goes_schema import (
    GoesXrsResponse,
    GoesProtonResponse,
    GoesXrsLatest,
    GoesProtonLatest,
)
from app.services.goes_xrs_service import get_goes_xrs, get_goes_xrs_latest
from app.services.goes_proton_service import get_goes_proton, get_goes_proton_latest

router = APIRouter(prefix="/api/goes", tags=["goes"])


def _parse_range(start: str | None, end: str | None) -> tuple[datetime, datetime]:
    now = datetime.now(timezone.utc)
    def _parse(s: str) -> datetime:
        return datetime.fromisoformat(s.replace("Z", "+00:00").replace(" ", "+"))

    try:
        t_end = _parse(end) if end else now
        t_start = _parse(start) if start else t_end - timedelta(days=1)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid datetime: {exc}") from exc
    if t_start >= t_end:
        raise HTTPException(status_code=400, detail="start must be before end")
    if (t_end - t_start).days > 7:
        raise HTTPException(status_code=400, detail="Date range must be 7 days or less")
    return t_start, t_end


@router.get("/xrs/latest", response_model=GoesXrsLatest)
async def goes_xrs_latest() -> GoesXrsLatest:
    return await get_goes_xrs_latest()


@router.get("/xrs", response_model=GoesXrsResponse)
async def goes_xrs(
    start: str | None = Query(None),
    end: str | None = Query(None),
) -> GoesXrsResponse:
    t_start, t_end = _parse_range(start, end)
    return await get_goes_xrs(t_start, t_end)


@router.get("/proton/latest", response_model=GoesProtonLatest)
async def goes_proton_latest() -> GoesProtonLatest:
    return await get_goes_proton_latest()


@router.get("/proton", response_model=GoesProtonResponse)
async def goes_proton(
    start: str | None = Query(None),
    end: str | None = Query(None),
) -> GoesProtonResponse:
    t_start, t_end = _parse_range(start, end)
    return await get_goes_proton(t_start, t_end)
