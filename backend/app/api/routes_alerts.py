from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Query

from app.schemas.alert_schema import AlertResponse, EventResponse

router = APIRouter(prefix="/api", tags=["alerts"])


@router.get("/alerts/latest", response_model=list[AlertResponse])
async def alerts_latest() -> list[AlertResponse]:
    # Placeholder — real alert engine wired in Phase 10
    return []


@router.get("/events", response_model=list[EventResponse])
async def events(
    start: str | None = Query(None),
    end: str | None = Query(None),
) -> list[EventResponse]:
    # Placeholder — returns empty list until event DB is populated
    return []
