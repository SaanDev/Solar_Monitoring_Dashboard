from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.repositories.status_repo import get_all
from app.schemas.status_schema import StatusResponse, SourceStatus, SourcesStatusResponse

router = APIRouter(prefix="/api", tags=["status"])

# Sources surfaced in the UI. The first four are ingested on a schedule and their
# health comes from the source_status table; the rest are not yet wired and stay
# "unknown" until their collectors are added.
_KNOWN_SOURCES = [
    "GOES-XRS",
    "GOES-Proton",
    "Kp-Index",
    "Dst-Index",
    "Solar-Wind",
    "SDO-AIA",
    "SOHO-LASCO",
    "e-CALLISTO",
]


@router.get("/status", response_model=StatusResponse)
async def get_status() -> StatusResponse:
    return StatusResponse(
        service="space-weather-dashboard",
        status="ok",
        timestamp=datetime.now(timezone.utc),
        version=settings.version,
    )


@router.get("/sources/status", response_model=SourcesStatusResponse)
async def get_sources_status(db: AsyncSession = Depends(get_db)) -> SourcesStatusResponse:
    try:
        recorded = await get_all(db)
    except Exception:
        recorded = {}

    sources = []
    for name in _KNOWN_SOURCES:
        row = recorded.get(name)
        if row is None:
            sources.append(SourceStatus(name=name, status="unknown", last_updated=None))
        else:
            sources.append(
                SourceStatus(
                    name=name,
                    status=row.status,
                    last_updated=row.last_success_at,
                    message=row.last_error,
                )
            )
    return SourcesStatusResponse(sources=sources)
