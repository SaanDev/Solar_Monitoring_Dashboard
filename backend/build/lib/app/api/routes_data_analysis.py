"""SDO/AIA Data Analysis API.

Sessions hold solar FITS frames (upload / Fido fetch / JSOC archive); single-image
plot+crop renders synchronously, while sequence work (fetch, difference, movie)
runs as a background job polled via ``/jobs/{job_id}`` with the artifact served from
``/result/{job_id}``.
"""
from __future__ import annotations

import mimetypes
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse

from datetime import datetime

from app.schemas.data_analysis_schema import (
    AnalysisOptions,
    AnalysisSession,
    ArchiveRequest,
    FetchRequest,
    JobStatusResponse,
    MovieRequest,
    SequenceRequest,
)
from app.services import aia_analysis_service as analysis
from app.services import aia_data_service as data
from app.services.aia_analysis_service import COLORMAPS, SCALES, PlotParams
from app.services.job_manager import Job, job_manager

router = APIRouter(prefix="/api/analysis", tags=["analysis"])

_MAX_UPLOAD_FRAMES = 60
_FITS_SUFFIXES = (".fit", ".fits", ".fit.gz", ".fits.gz", ".fz")


@router.get("/options", response_model=AnalysisOptions)
async def options() -> AnalysisOptions:
    return AnalysisOptions(
        wavelengths=data.wavelength_options(),
        colormaps=COLORMAPS,
        scales=SCALES,
        difference_types=["running", "base"],
        movie_formats=["mp4", "gif"],
        max_frames=40,
    )


@router.post("/source/upload", response_model=AnalysisSession)
async def upload(files: list[UploadFile] = File(...)) -> AnalysisSession:
    if not files:
        raise HTTPException(400, "No files uploaded")
    if len(files) > _MAX_UPLOAD_FRAMES:
        raise HTTPException(400, f"At most {_MAX_UPLOAD_FRAMES} frames per session")
    payload: list[tuple[bytes, str]] = []
    for f in files:
        name = (f.filename or "").lower()
        if not name.endswith(_FITS_SUFFIXES):
            raise HTTPException(400, f"{f.filename}: must be a FITS file (.fits/.fit/.fz)")
        payload.append((await f.read(), f.filename or "upload.fits"))
    try:
        return data.store_upload(payload)
    except Exception as exc:  # noqa: BLE001 - surface load failures to the client
        raise HTTPException(422, f"FITS could not be read as a solar map: {exc}") from exc


@router.post("/source/fetch", response_model=JobStatusResponse)
async def source_fetch(req: FetchRequest) -> JobStatusResponse:
    """Start a background Fido download of the AIA frame nearest a UTC time."""
    if req.wavelength not in {w.code for w in data.wavelength_options()}:
        raise HTTPException(422, f"Unknown AIA wavelength: {req.wavelength}")
    job_id = job_manager.submit(
        data.fetch_via_fido, req.wavelength, req.time, req.prep
    )
    job = job_manager.get(job_id)
    assert job is not None
    return _job_response(job)


@router.post("/source/archive", response_model=AnalysisSession)
async def source_archive(req: ArchiveRequest) -> AnalysisSession:
    """Pull a 1024px synoptic AIA frame from the existing JSOC archive (fast path)."""
    if req.wavelength not in {w.code for w in data.wavelength_options()}:
        raise HTTPException(422, f"Unknown AIA wavelength: {req.wavelength}")
    try:
        d = datetime.strptime(req.date, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(400, "date must be YYYY-MM-DD")
    result = await data.store_from_archive(d, req.time, req.wavelength)
    if result is None:
        raise HTTPException(404, f"No archive FITS for AIA {req.wavelength} on {req.date}")
    return result


@router.post("/source/sequence", response_model=JobStatusResponse)
async def source_sequence(req: SequenceRequest) -> JobStatusResponse:
    """Start a background build of a multi-frame session from the JSOC archive."""
    if req.wavelength not in {w.code for w in data.wavelength_options()}:
        raise HTTPException(422, f"Unknown AIA wavelength: {req.wavelength}")
    try:
        datetime.strptime(req.date, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(400, "date must be YYYY-MM-DD")
    job_id = job_manager.submit(
        data.fetch_archive_sequence,
        req.date, req.start_time, req.step_min, req.n_frames, req.wavelength,
    )
    job = job_manager.get(job_id)
    assert job is not None
    return _job_response(job)


@router.get("/session/{session_id}", response_model=AnalysisSession)
async def session(session_id: str) -> AnalysisSession:
    try:
        return data.get_session(session_id)
    except FileNotFoundError:
        raise HTTPException(404, "Analysis session not found")
    except ValueError as exc:
        raise HTTPException(400, str(exc))


def _plot_params(
    cmap: str,
    scale: str,
    clip_low: float,
    clip_high: float,
    vmin: float | None,
    vmax: float | None,
    crop: bool,
    bl_x: float,
    bl_y: float,
    tr_x: float,
    tr_y: float,
    draw_limb: bool,
    draw_grid: bool,
    colorbar: bool,
) -> PlotParams:
    if cmap not in COLORMAPS:
        raise HTTPException(422, f"cmap must be one of {COLORMAPS}")
    if scale not in SCALES:
        raise HTTPException(422, f"scale must be one of {SCALES}")
    return PlotParams(
        cmap=cmap, scale=scale, clip_low=clip_low, clip_high=clip_high,
        vmin=vmin, vmax=vmax, crop=crop, bl_x=bl_x, bl_y=bl_y, tr_x=tr_x, tr_y=tr_y,
        draw_limb=draw_limb, draw_grid=draw_grid, colorbar=colorbar,
    )


@router.get("/render")
async def render(
    session: str = Query(...),
    frame: int = Query(0),
    cmap: str = Query("auto"),
    scale: str = Query("linear"),
    clip_low: float = Query(1.0),
    clip_high: float = Query(99.9),
    vmin: float | None = Query(None),
    vmax: float | None = Query(None),
    crop: bool = Query(False),
    bl_x: float = Query(0.0),
    bl_y: float = Query(0.0),
    tr_x: float = Query(0.0),
    tr_y: float = Query(0.0),
    draw_limb: bool = Query(False),
    draw_grid: bool = Query(False),
    colorbar: bool = Query(True),
    download: bool = Query(False),
) -> FileResponse:
    params = _plot_params(
        cmap, scale, clip_low, clip_high, vmin, vmax,
        crop, bl_x, bl_y, tr_x, tr_y, draw_limb, draw_grid, colorbar,
    )
    dpi = analysis.EXPORT_DPI if download else analysis.RENDER_DPI
    try:
        path = analysis.render_plot(session, frame, params, dpi=dpi)
    except FileNotFoundError:
        raise HTTPException(404, "Analysis session not found")
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    headers = {}
    if download:
        headers["Content-Disposition"] = f'attachment; filename="aia_{session[:8]}_{frame}.png"'
    return FileResponse(path, media_type="image/png", headers=headers)


@router.get("/difference")
async def difference(
    session: str = Query(...),
    frame: int = Query(...),
    diff_type: str = Query("running", pattern="^(running|base)$"),
    base_index: int = Query(0),
    cmap: str = Query("auto"),
    clip_high: float = Query(99.0),
    vmin: float | None = Query(None),
    vmax: float | None = Query(None),
    crop: bool = Query(False),
    bl_x: float = Query(0.0),
    bl_y: float = Query(0.0),
    tr_x: float = Query(0.0),
    tr_y: float = Query(0.0),
    draw_limb: bool = Query(False),
    draw_grid: bool = Query(False),
    colorbar: bool = Query(True),
    download: bool = Query(False),
) -> FileResponse:
    params = _plot_params(
        cmap, "linear", 1.0, clip_high, vmin, vmax,
        crop, bl_x, bl_y, tr_x, tr_y, draw_limb, draw_grid, colorbar,
    )
    dpi = analysis.EXPORT_DPI if download else analysis.RENDER_DPI
    try:
        path = analysis.render_difference(session, frame, diff_type, base_index, params, dpi=dpi)
    except FileNotFoundError:
        raise HTTPException(404, "Analysis session or frame not found")
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    headers = {}
    if download:
        headers["Content-Disposition"] = (
            f'attachment; filename="aia_{session[:8]}_{diff_type}diff_{frame}.png"'
        )
    return FileResponse(path, media_type="image/png", headers=headers)


@router.get("/composite")
async def composite(
    session: str = Query(...),
    frame: int = Query(0),
    contour_level: float = Query(100.0, description="HMI |B| contour level in Gauss"),
    cmap: str = Query("auto"),
    scale: str = Query("sqrt"),
    clip_low: float = Query(1.0),
    clip_high: float = Query(99.9),
    vmin: float | None = Query(None),
    vmax: float | None = Query(None),
    crop: bool = Query(False),
    bl_x: float = Query(0.0),
    bl_y: float = Query(0.0),
    tr_x: float = Query(0.0),
    tr_y: float = Query(0.0),
    draw_limb: bool = Query(False),
    draw_grid: bool = Query(False),
    colorbar: bool = Query(True),
    download: bool = Query(False),
) -> FileResponse:
    params = _plot_params(
        cmap, scale, clip_low, clip_high, vmin, vmax,
        crop, bl_x, bl_y, tr_x, tr_y, draw_limb, draw_grid, colorbar,
    )
    try:
        when = data.frame_time(session, frame)
    except FileNotFoundError:
        raise HTTPException(404, "Analysis session or frame not found")
    if when is None:
        raise HTTPException(422, "This frame has no timestamp; composite needs a dated frame.")
    hmi_bytes = await data.fetch_hmi_bytes(when.date(), when.strftime("%H:%M"))
    dpi = analysis.EXPORT_DPI if download else analysis.RENDER_DPI
    try:
        path = analysis.render_composite(session, frame, hmi_bytes, params, contour_level, dpi=dpi)
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    headers = {}
    if download:
        headers["Content-Disposition"] = f'attachment; filename="aia_{session[:8]}_composite_{frame}.png"'
    return FileResponse(path, media_type="image/png", headers=headers)


@router.get("/active-regions")
async def active_regions(
    session: str = Query(...),
    frame: int = Query(0),
    method: str = Query("hek", pattern="^(hek|threshold)$"),
    threshold_pct: float = Query(95.0),
    cmap: str = Query("auto"),
    scale: str = Query("sqrt"),
    clip_low: float = Query(1.0),
    clip_high: float = Query(99.9),
    vmin: float | None = Query(None),
    vmax: float | None = Query(None),
    crop: bool = Query(False),
    bl_x: float = Query(0.0),
    bl_y: float = Query(0.0),
    tr_x: float = Query(0.0),
    tr_y: float = Query(0.0),
    draw_limb: bool = Query(False),
    draw_grid: bool = Query(False),
    colorbar: bool = Query(True),
    download: bool = Query(False),
) -> FileResponse:
    params = _plot_params(
        cmap, scale, clip_low, clip_high, vmin, vmax,
        crop, bl_x, bl_y, tr_x, tr_y, draw_limb, draw_grid, colorbar,
    )
    ar_list: list = []
    if method == "hek":
        try:
            when = data.frame_time(session, frame)
        except FileNotFoundError:
            raise HTTPException(404, "Analysis session or frame not found")
        if when is not None:
            ar_list = await data.fetch_hek_active_regions(when.date(), when.strftime("%H:%M"))
    dpi = analysis.EXPORT_DPI if download else analysis.RENDER_DPI
    try:
        path = analysis.render_active_regions(
            session, frame, method, ar_list, threshold_pct, params, dpi=dpi
        )
    except FileNotFoundError:
        raise HTTPException(404, "Analysis session or frame not found")
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    headers = {}
    if download:
        headers["Content-Disposition"] = f'attachment; filename="aia_{session[:8]}_ar_{method}_{frame}.png"'
    return FileResponse(path, media_type="image/png", headers=headers)


@router.post("/movie", response_model=JobStatusResponse)
async def movie(req: MovieRequest) -> JobStatusResponse:
    """Start a background time-lapse render; poll /jobs and fetch from /result."""
    if req.fmt not in ("mp4", "gif"):
        raise HTTPException(422, "fmt must be mp4 or gif")
    if req.mode not in ("plot", "difference"):
        raise HTTPException(422, "mode must be plot or difference")
    if req.cmap not in COLORMAPS:
        raise HTTPException(422, f"cmap must be one of {COLORMAPS}")
    if req.scale not in SCALES:
        raise HTTPException(422, f"scale must be one of {SCALES}")
    params = PlotParams(
        cmap=req.cmap, scale=req.scale, clip_low=req.clip_low, clip_high=req.clip_high,
        crop=req.crop, bl_x=req.bl_x, bl_y=req.bl_y, tr_x=req.tr_x, tr_y=req.tr_y,
    )
    job_id = job_manager.submit(
        analysis.make_movie, req.session, req.fmt, req.fps, req.mode, params
    )
    job = job_manager.get(job_id)
    assert job is not None
    return _job_response(job)


# ── background jobs ─────────────────────────────────────────────────────────────


def _job_response(job: Job) -> JobStatusResponse:
    resp = JobStatusResponse(
        job_id=job.id,
        state=job.state,
        progress=job.progress,
        message=job.message,
        error=job.error,
    )
    meta = job.result_meta or {}
    if job.state == "done":
        if meta.get("kind") == "session" and meta.get("session"):
            resp.session = AnalysisSession.model_validate(meta["session"])
        elif meta.get("kind") == "artifact":
            resp.result_url = f"/api/analysis/result/{job.id}"
            resp.meta = {k: v for k, v in meta.items() if k != "kind"}
    return resp


@router.get("/jobs/{job_id}", response_model=JobStatusResponse)
async def job_status(job_id: str) -> JobStatusResponse:
    job = job_manager.get(job_id)
    if job is None:
        raise HTTPException(404, "Job not found")
    return _job_response(job)


@router.get("/result/{job_id}")
async def job_result(job_id: str, download: bool = Query(False)) -> FileResponse:
    job = job_manager.get(job_id)
    if job is None:
        raise HTTPException(404, "Job not found")
    if job.state != "done" or not job.result_path:
        raise HTTPException(409, "Job result not ready")
    path = Path(job.result_path)
    if not path.exists():
        raise HTTPException(404, "Job artifact missing")
    media = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    headers = {}
    if download:
        headers["Content-Disposition"] = f'attachment; filename="{path.name}"'
    return FileResponse(path, media_type=media, headers=headers)
