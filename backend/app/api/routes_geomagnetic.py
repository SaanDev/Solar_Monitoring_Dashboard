from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Query, HTTPException

from app.schemas.geomagnetic_schema import KpPoint, DstPoint, KpLatest, DstLatest
from app.services.kp_service import get_kp, get_kp_latest
from app.services.dst_service import get_dst, get_dst_latest

router = APIRouter(prefix="/api/geomagnetic", tags=["geomagnetic"])


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
    return t_start, t_end


@router.get("/kp/latest", response_model=KpLatest)
async def kp_latest() -> KpLatest:
    return await get_kp_latest()


@router.get("/dst/latest", response_model=DstLatest)
async def dst_latest() -> DstLatest:
    return await get_dst_latest()


@router.get("/kp", response_model=list[KpPoint])
async def kp_index(
    start: str | None = Query(None),
    end: str | None = Query(None),
) -> list[KpPoint]:
    t_start, t_end = _parse_range(start, end)
    return await get_kp(t_start, t_end)


@router.get("/dst", response_model=list[DstPoint])
async def dst_index(
    start: str | None = Query(None),
    end: str | None = Query(None),
) -> list[DstPoint]:
    t_start, t_end = _parse_range(start, end)
    return await get_dst(t_start, t_end)
