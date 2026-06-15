from datetime import datetime, timezone

from fastapi import APIRouter

from app.config import settings
from app.schemas.status_schema import StatusResponse, SourceStatus, SourcesStatusResponse

router = APIRouter(prefix="/api", tags=["status"])

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
async def get_sources_status() -> SourcesStatusResponse:
    sources = [
        SourceStatus(name=name, status="unknown", last_updated=None)
        for name in _KNOWN_SOURCES
    ]
    return SourcesStatusResponse(sources=sources)
