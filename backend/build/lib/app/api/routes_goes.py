import csv
import io
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Query, HTTPException, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.processing.flux_plot import render_xrs_png, render_proton_png
from app.schemas.goes_schema import (
    GoesXrsResponse,
    GoesProtonResponse,
    GoesXrsLatest,
    GoesProtonLatest,
    GoesElectronResponse,
    GoesElectronLatest,
    GoesMagnetometerResponse,
    GoesMagnetometerLatest,
)
from app.services.goes_xrs_service import get_goes_xrs, get_goes_xrs_latest
from app.services.goes_proton_service import get_goes_proton, get_goes_proton_latest
from app.services.goes_electron_service import get_goes_electron, get_goes_electron_latest
from app.services.goes_magnetometer_service import (
    get_goes_magnetometer,
    get_goes_magnetometer_latest,
)

router = APIRouter(prefix="/api/goes", tags=["goes"])


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
    if (t_end - t_start).days > 7:
        raise HTTPException(status_code=400, detail="Date range must be 7 days or less")
    return t_start, t_end


@router.get("/xrs/latest", response_model=GoesXrsLatest)
async def goes_xrs_latest(db: AsyncSession = Depends(get_db)) -> GoesXrsLatest:
    return await get_goes_xrs_latest(db)


@router.get("/xrs", response_model=GoesXrsResponse)
async def goes_xrs(
    start: str | None = Query(None),
    end: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
) -> GoesXrsResponse:
    t_start, t_end = _parse_range(start, end)
    return await get_goes_xrs(db, t_start, t_end)


@router.get("/proton/latest", response_model=GoesProtonLatest)
async def goes_proton_latest(db: AsyncSession = Depends(get_db)) -> GoesProtonLatest:
    return await get_goes_proton_latest(db)


@router.get("/proton", response_model=GoesProtonResponse)
async def goes_proton(
    start: str | None = Query(None),
    end: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
) -> GoesProtonResponse:
    t_start, t_end = _parse_range(start, end)
    return await get_goes_proton(db, t_start, t_end)


# ─── Archive downloads: raw data (CSV/JSON) + rendered plot (PNG) ────────────


@router.get("/xrs/download")
async def xrs_download(
    start: str | None = Query(None),
    end: str | None = Query(None),
    format: str = Query("csv", pattern="^(csv|json)$"),
    db: AsyncSession = Depends(get_db),
) -> Response:
    t_start, t_end = _parse_range(start, end)
    resp = await get_goes_xrs(db, t_start, t_end)
    if format == "json":
        return Response(
            content=resp.model_dump_json(indent=2),
            media_type="application/json",
            headers=_attach(f"goes_xrs_{_stamp(t_start, t_end)}.json"),
        )
    rows = [[p.time.isoformat(), p.short_channel, p.long_channel] for p in resp.data]
    body = _csv(["time", "short_channel_wm2", "long_channel_wm2"], rows)
    return Response(
        content=body, media_type="text/csv",
        headers=_attach(f"goes_xrs_{_stamp(t_start, t_end)}.csv"),
    )


@router.get("/xrs/plot")
async def xrs_plot(
    start: str | None = Query(None),
    end: str | None = Query(None),
    download: bool = Query(False),
    db: AsyncSession = Depends(get_db),
) -> Response:
    t_start, t_end = _parse_range(start, end)
    resp = await get_goes_xrs(db, t_start, t_end)
    png = render_xrs_png(resp.data)
    headers = _attach(f"goes_xrs_{_stamp(t_start, t_end)}.png") if download else {}
    return Response(content=png, media_type="image/png", headers=headers)


@router.get("/proton/download")
async def proton_download(
    start: str | None = Query(None),
    end: str | None = Query(None),
    format: str = Query("csv", pattern="^(csv|json)$"),
    db: AsyncSession = Depends(get_db),
) -> Response:
    t_start, t_end = _parse_range(start, end)
    resp = await get_goes_proton(db, t_start, t_end)
    if format == "json":
        return Response(
            content=resp.model_dump_json(indent=2),
            media_type="application/json",
            headers=_attach(f"goes_proton_{_stamp(t_start, t_end)}.json"),
        )
    rows = [[p.time.isoformat(), p.flux_gt10, p.flux_gt50, p.flux_gt100] for p in resp.data]
    body = _csv(["time", "flux_gt10_pfu", "flux_gt50_pfu", "flux_gt100_pfu"], rows)
    return Response(
        content=body, media_type="text/csv",
        headers=_attach(f"goes_proton_{_stamp(t_start, t_end)}.csv"),
    )


@router.get("/proton/plot")
async def proton_plot(
    start: str | None = Query(None),
    end: str | None = Query(None),
    download: bool = Query(False),
    db: AsyncSession = Depends(get_db),
) -> Response:
    t_start, t_end = _parse_range(start, end)
    resp = await get_goes_proton(db, t_start, t_end)
    png = render_proton_png(resp.data)
    headers = _attach(f"goes_proton_{_stamp(t_start, t_end)}.png") if download else {}
    return Response(content=png, media_type="image/png", headers=headers)


# ─── GOES electron flux (>=2 MeV) ────────────────────────────────────────────


@router.get("/electrons/latest", response_model=GoesElectronLatest)
async def goes_electrons_latest(db: AsyncSession = Depends(get_db)) -> GoesElectronLatest:
    return await get_goes_electron_latest(db)


@router.get("/electrons", response_model=GoesElectronResponse)
async def goes_electrons(
    start: str | None = Query(None),
    end: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
) -> GoesElectronResponse:
    t_start, t_end = _parse_range(start, end)
    return await get_goes_electron(db, t_start, t_end)


@router.get("/electrons/download")
async def electrons_download(
    start: str | None = Query(None),
    end: str | None = Query(None),
    format: str = Query("csv", pattern="^(csv|json)$"),
    db: AsyncSession = Depends(get_db),
) -> Response:
    t_start, t_end = _parse_range(start, end)
    resp = await get_goes_electron(db, t_start, t_end)
    if format == "json":
        return Response(
            content=resp.model_dump_json(indent=2),
            media_type="application/json",
            headers=_attach(f"goes_electrons_{_stamp(t_start, t_end)}.json"),
        )
    rows = [[p.time.isoformat(), p.flux_ge2mev] for p in resp.data]
    body = _csv(["time", "flux_ge2mev"], rows)
    return Response(
        content=body, media_type="text/csv",
        headers=_attach(f"goes_electrons_{_stamp(t_start, t_end)}.csv"),
    )


# ─── GOES magnetometer (Hp / He / Hn + total, nT) ────────────────────────────


@router.get("/magnetometer/latest", response_model=GoesMagnetometerLatest)
async def goes_magnetometer_latest(db: AsyncSession = Depends(get_db)) -> GoesMagnetometerLatest:
    return await get_goes_magnetometer_latest(db)


@router.get("/magnetometer", response_model=GoesMagnetometerResponse)
async def goes_magnetometer(
    start: str | None = Query(None),
    end: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
) -> GoesMagnetometerResponse:
    t_start, t_end = _parse_range(start, end)
    return await get_goes_magnetometer(db, t_start, t_end)


@router.get("/magnetometer/download")
async def magnetometer_download(
    start: str | None = Query(None),
    end: str | None = Query(None),
    format: str = Query("csv", pattern="^(csv|json)$"),
    db: AsyncSession = Depends(get_db),
) -> Response:
    t_start, t_end = _parse_range(start, end)
    resp = await get_goes_magnetometer(db, t_start, t_end)
    if format == "json":
        return Response(
            content=resp.model_dump_json(indent=2),
            media_type="application/json",
            headers=_attach(f"goes_magnetometer_{_stamp(t_start, t_end)}.json"),
        )
    rows = [[p.time.isoformat(), p.hp, p.he, p.hn, p.total] for p in resp.data]
    body = _csv(["time", "hp_nt", "he_nt", "hn_nt", "total_nt"], rows)
    return Response(
        content=body, media_type="text/csv",
        headers=_attach(f"goes_magnetometer_{_stamp(t_start, t_end)}.csv"),
    )
