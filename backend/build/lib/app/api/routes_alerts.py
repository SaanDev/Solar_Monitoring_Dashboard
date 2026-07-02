from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas.alert_schema import AlertResponse, EventResponse
from app.services.event_service import get_events, get_latest_alerts

router = APIRouter(prefix="/api", tags=["alerts"])

# Events are sparse and worth browsing over the full record, so the window is
# effectively unbounded (decades) unlike the 7-day cap on the dense numeric feeds.
_MAX_RANGE_DAYS = 366 * 50


def _parse_range(start: str | None, end: str | None) -> tuple[datetime, datetime]:
    now = datetime.now(timezone.utc)

    def _parse(s: str) -> datetime:
        return datetime.fromisoformat(s.replace("Z", "+00:00").replace(" ", "+"))

    try:
        t_end = _parse(end) if end else now
        t_start = _parse(start) if start else t_end - timedelta(days=30)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid datetime: {exc}") from exc
    if t_start >= t_end:
        raise HTTPException(status_code=400, detail="start must be before end")
    if (t_end - t_start).days > _MAX_RANGE_DAYS:
        raise HTTPException(
            status_code=400, detail=f"Date range must be {_MAX_RANGE_DAYS} days or less"
        )
    return t_start, t_end


@router.get("/alerts/latest", response_model=list[AlertResponse])
async def alerts_latest(db: AsyncSession = Depends(get_db)) -> list[AlertResponse]:
    return await get_latest_alerts(db)


@router.get("/events", response_model=list[EventResponse])
async def events(
    start: str | None = Query(None),
    end: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
) -> list[EventResponse]:
    t_start, t_end = _parse_range(start, end)
    return await get_events(db, t_start, t_end)
