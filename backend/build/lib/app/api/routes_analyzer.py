"""Interactive e-CALLISTO Analyzer API: import a FITS, re-render on control change,
export PNG / processed FITS."""
from datetime import date as date_cls, datetime
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, Query, Response, UploadFile
from fastapi.responses import FileResponse

from app.processing.analyzer_processing import (
    BACKGROUND_METHODS,
    COLORMAPS,
    INTENSITY_UNITS,
    TIME_UNITS,
)
from app.schemas.analyzer_schema import (
    AnalyzerSession,
    AnalyzerStats,
    ProjectOpenResponse,
)
from app.services import analyzer_service as svc
from app.services.analyzer_service import RenderParams

router = APIRouter(prefix="/api/analyzer", tags=["analyzer"])


def _parse_date(value: str) -> date_cls:
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="date must be YYYY-MM-DD") from exc


def _params(
    method: str,
    intensity_unit: str,
    time_unit: str,
    cmap: str,
    vmin: float | None,
    vmax: float | None,
    rfi_enabled: bool,
    rfi_low: float,
    rfi_high: float,
    station: str,
) -> RenderParams:
    if method not in BACKGROUND_METHODS:
        raise HTTPException(422, f"method must be one of {BACKGROUND_METHODS}")
    if intensity_unit not in INTENSITY_UNITS:
        raise HTTPException(422, f"intensity_unit must be one of {INTENSITY_UNITS}")
    if time_unit not in TIME_UNITS:
        raise HTTPException(422, f"time_unit must be one of {TIME_UNITS}")
    if cmap not in COLORMAPS:
        raise HTTPException(422, f"cmap must be one of {COLORMAPS}")
    return RenderParams(
        method=method,
        intensity_unit=intensity_unit,
        time_unit=time_unit,
        cmap=cmap,
        vmin=vmin,
        vmax=vmax,
        rfi_enabled=rfi_enabled,
        rfi_low=rfi_low,
        rfi_high=rfi_high,
        station=station,
    )


@router.get("/colormaps")
async def colormaps() -> dict:
    return {
        "colormaps": list(COLORMAPS),
        "methods": list(BACKGROUND_METHODS),
        "intensity_units": list(INTENSITY_UNITS),
        "time_units": list(TIME_UNITS),
    }


@router.post("/upload", response_model=AnalyzerSession)
async def upload(
    file: UploadFile = File(...),
    station: str = Form(""),
) -> AnalyzerSession:
    name = (file.filename or "").lower()
    if not name.endswith((".fit", ".fits", ".fit.gz", ".fits.gz")):
        raise HTTPException(400, "File must be a FITS file (.fit, .fits, .fit.gz)")
    content = await file.read()
    try:
        return svc.store_upload(content, file.filename or "upload.fits", station)
    except Exception as exc:
        raise HTTPException(422, f"FITS could not be read: {exc}") from exc


@router.post("/from-archive", response_model=AnalyzerSession)
async def from_archive(
    date: str = Query(..., description="UTC date YYYY-MM-DD"),
    station: str = Query(...),
    filename: str = Query(...),
) -> AnalyzerSession:
    result = await svc.store_from_archive(_parse_date(date), station, filename)
    if result is None:
        raise HTTPException(404, f"Archive FITS not found: {filename}")
    return result


@router.post("/combine", response_model=AnalyzerSession)
async def combine(
    ids: list[str] = Query(..., description="Two or more session ids"),
    mode: str = Query(..., pattern="^(time|frequency)$"),
) -> AnalyzerSession:
    if len(ids) < 2:
        raise HTTPException(422, "Select at least 2 files to combine")
    try:
        return svc.combine(ids, mode)
    except FileNotFoundError:
        raise HTTPException(404, "Analyzer session not found")
    except ValueError as exc:
        raise HTTPException(422, str(exc))


@router.get("/stats", response_model=AnalyzerStats)
async def stats(
    id: str = Query(...),
    method: str = Query("median"),
    intensity_unit: str = Query("db"),
    rfi_enabled: bool = Query(False),
    rfi_low: float = Query(1.0),
    rfi_high: float = Query(99.0),
) -> AnalyzerStats:
    params = _params(
        method, intensity_unit, "seconds", "magma", None, None,
        rfi_enabled, rfi_low, rfi_high, "",
    )
    try:
        return svc.compute_stats(id, params)
    except FileNotFoundError:
        raise HTTPException(404, "Analyzer session not found")
    except ValueError as exc:
        raise HTTPException(422, str(exc))


@router.get("/render")
async def render(
    id: str = Query(...),
    method: str = Query("median"),
    intensity_unit: str = Query("db"),
    time_unit: str = Query("seconds"),
    cmap: str = Query("magma"),
    vmin: float | None = Query(None),
    vmax: float | None = Query(None),
    rfi_enabled: bool = Query(False),
    rfi_low: float = Query(1.0),
    rfi_high: float = Query(99.0),
    station: str = Query(""),
) -> FileResponse:
    params = _params(
        method, intensity_unit, time_unit, cmap, vmin, vmax,
        rfi_enabled, rfi_low, rfi_high, station,
    )
    try:
        path = svc.render(id, params)
    except FileNotFoundError:
        raise HTTPException(404, "Analyzer session not found")
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    return FileResponse(path, media_type="image/png")


@router.get("/export")
async def export(
    id: str = Query(...),
    format: str = Query("png", pattern="^(png|fits)$"),
    method: str = Query("median"),
    intensity_unit: str = Query("db"),
    time_unit: str = Query("seconds"),
    cmap: str = Query("magma"),
    vmin: float | None = Query(None),
    vmax: float | None = Query(None),
    rfi_enabled: bool = Query(False),
    rfi_low: float = Query(1.0),
    rfi_high: float = Query(99.0),
    station: str = Query(""),
) -> Response:
    params = _params(
        method, intensity_unit, time_unit, cmap, vmin, vmax,
        rfi_enabled, rfi_low, rfi_high, station,
    )
    try:
        if format == "fits":
            content, fname = svc.export_fits(id, params)
            return Response(
                content=content,
                media_type="application/fits",
                headers={"Content-Disposition": f'attachment; filename="{fname}"'},
            )
        path = svc.render(id, params, dpi=svc.EXPORT_DPI)  # extra-sharp download
    except FileNotFoundError:
        raise HTTPException(404, "Analyzer session not found")
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    fname = f"analyzer_{id[:8]}_{params.intensity_unit}.png"
    return FileResponse(
        Path(path), media_type="image/png",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


@router.get("/project")
async def project(
    id: str = Query(...),
    method: str = Query("median"),
    intensity_unit: str = Query("db"),
    time_unit: str = Query("seconds"),
    cmap: str = Query("magma"),
    vmin: float | None = Query(None),
    vmax: float | None = Query(None),
    rfi_enabled: bool = Query(False),
    rfi_low: float = Query(1.0),
    rfi_high: float = Query(99.0),
    station: str = Query(""),
) -> Response:
    """Download the session as a .efaproj project (opens in the desktop app too)."""
    params = _params(
        method, intensity_unit, time_unit, cmap, vmin, vmax,
        rfi_enabled, rfi_low, rfi_high, station,
    )
    try:
        content, fname = svc.save_project(id, params)
    except FileNotFoundError:
        raise HTTPException(404, "Analyzer session not found")
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    return Response(
        content=content,
        media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


@router.post("/open-project", response_model=ProjectOpenResponse)
async def open_project(file: UploadFile = File(...)) -> ProjectOpenResponse:
    """Open a .efaproj project (from web or desktop) into a new session."""
    name = (file.filename or "").lower()
    if not name.endswith(".efaproj"):
        raise HTTPException(400, "File must be a .efaproj project")
    content = await file.read()
    try:
        session, settings = svc.open_project(content)
    except Exception as exc:
        raise HTTPException(422, f"Could not open project: {exc}")
    return ProjectOpenResponse(session=session, settings=settings)
