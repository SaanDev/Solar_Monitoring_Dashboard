import csv
import io
import json
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Query, HTTPException, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.processing.flux_plot import render_kp_png, render_dst_png
from app.schemas.geomagnetic_schema import KpPoint, DstPoint, KpLatest, DstLatest
from app.services.kp_service import get_kp, get_kp_latest
from app.services.dst_service import get_dst, get_dst_latest

router = APIRouter(prefix="/api/geomagnetic", tags=["geomagnetic"])


def _csv(header: list[str], rows: list[list]) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(header)
    w.writerows(rows)
    return buf.getvalue()


def _attach(name: str) -> dict:
    return {"Content-Disposition": f'attachment; filename="{name}"'}


def _stamp(start: datetime, end: datetime) -> str:
    return f"{start:%Y%m%dT%H%M}_{end:%Y%m%dT%H%M}"


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
async def kp_latest(db: AsyncSession = Depends(get_db)) -> KpLatest:
    return await get_kp_latest(db)


@router.get("/dst/latest", response_model=DstLatest)
async def dst_latest(db: AsyncSession = Depends(get_db)) -> DstLatest:
    return await get_dst_latest(db)


@router.get("/kp", response_model=list[KpPoint])
async def kp_index(
    start: str | None = Query(None),
    end: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
) -> list[KpPoint]:
    t_start, t_end = _parse_range(start, end)
    return await get_kp(db, t_start, t_end)


@router.get("/dst", response_model=list[DstPoint])
async def dst_index(
    start: str | None = Query(None),
    end: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
) -> list[DstPoint]:
    t_start, t_end = _parse_range(start, end)
    return await get_dst(db, t_start, t_end)


# ─── Archive downloads: raw data (CSV/JSON) + rendered plot (PNG) ────────────


@router.get("/kp/download")
async def kp_download(
    start: str | None = Query(None),
    end: str | None = Query(None),
    format: str = Query("csv", pattern="^(csv|json)$"),
    db: AsyncSession = Depends(get_db),
) -> Response:
    t_start, t_end = _parse_range(start, end)
    points = await get_kp(db, t_start, t_end)
    if format == "json":
        body = json.dumps([p.model_dump(mode="json") for p in points], indent=2)
        return Response(content=body, media_type="application/json",
                        headers=_attach(f"kp_{_stamp(t_start, t_end)}.json"))
    body = _csv(["time", "kp"], [[p.time.isoformat(), p.kp] for p in points])
    return Response(content=body, media_type="text/csv",
                    headers=_attach(f"kp_{_stamp(t_start, t_end)}.csv"))


@router.get("/kp/plot")
async def kp_plot(
    start: str | None = Query(None),
    end: str | None = Query(None),
    download: bool = Query(False),
    db: AsyncSession = Depends(get_db),
) -> Response:
    t_start, t_end = _parse_range(start, end)
    points = await get_kp(db, t_start, t_end)
    png = render_kp_png(points)
    headers = _attach(f"kp_{_stamp(t_start, t_end)}.png") if download else {}
    return Response(content=png, media_type="image/png", headers=headers)


@router.get("/dst/download")
async def dst_download(
    start: str | None = Query(None),
    end: str | None = Query(None),
    format: str = Query("csv", pattern="^(csv|json)$"),
    db: AsyncSession = Depends(get_db),
) -> Response:
    t_start, t_end = _parse_range(start, end)
    points = await get_dst(db, t_start, t_end)
    if format == "json":
        body = json.dumps([p.model_dump(mode="json") for p in points], indent=2)
        return Response(content=body, media_type="application/json",
                        headers=_attach(f"dst_{_stamp(t_start, t_end)}.json"))
    body = _csv(["time", "dst_nt"], [[p.time.isoformat(), p.dst] for p in points])
    return Response(content=body, media_type="text/csv",
                    headers=_attach(f"dst_{_stamp(t_start, t_end)}.csv"))


@router.get("/dst/plot")
async def dst_plot(
    start: str | None = Query(None),
    end: str | None = Query(None),
    download: bool = Query(False),
    db: AsyncSession = Depends(get_db),
) -> Response:
    t_start, t_end = _parse_range(start, end)
    points = await get_dst(db, t_start, t_end)
    png = render_dst_png(points)
    headers = _attach(f"dst_{_stamp(t_start, t_end)}.png") if download else {}
    return Response(content=png, media_type="image/png", headers=headers)
