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
from pydantic import BaseModel

from datetime import datetime

from app.config import settings
from app.schemas.data_analysis_schema import (
    AnalysisOptions,
    AnalysisSession,
    ArchiveRequest,
    FetchRequest,
    FetchSelectionRequest,
    HeightTimeRequest,
    JMapRequest,
    JobStatusResponse,
    MovieRequest,
    SearchRequest,
    SearchResponse,
    SequenceRequest,
    VectorPrepareRequest,
)
from app.services import aia_analysis_service as analysis
from app.services import aia_data_service as data
from app.services import solar_acquisition_service as acquire
from app.services import solar_measure_service as measure
from app.services import solar_science_service as science
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
        observables=acquire.observable_options(),
        sources=["auto", "jsoc", "vso"],
        frame_sizes=["full", "bin2", "bin4", "cutout"],
        jsoc_enabled=bool(settings.jsoc_email),
    )


# ── multi-mission archive search (Fido) + selected-row download ──────────────────

_SCI_INSTALL_HINT = (
    "The multi-mission archive search needs the backend's scientific extras "
    "(SunPy/Fido). Install them where the backend runs: "
    'pip install -e ".[sci]" — or, when using Docker, rebuild the image '
    "(docker compose build backend && docker compose up -d backend) — then restart."
)


def _is_missing_dependency(exc: Exception) -> bool:
    """True when the failure is a missing scientific package, not a network/data
    problem (the ported acquisition layer wraps its lazy sunpy imports in
    RuntimeError with an install hint)."""
    if isinstance(exc, (ImportError, ModuleNotFoundError)):
        return True
    if isinstance(exc.__cause__, (ImportError, ModuleNotFoundError)):
        return True
    text = str(exc).lower()
    return "no module named" in text or "pip install" in text


@router.post("/source/search", response_model=SearchResponse)
async def source_search(req: SearchRequest) -> SearchResponse:
    """Search a mission archive (SunPy Fido). Rows are returned for the results
    table; the raw result is cached server-side under ``search_id`` for the
    follow-up download of selected rows."""
    import asyncio

    try:
        return await asyncio.to_thread(acquire.run_search, req)
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    except Exception as exc:  # noqa: BLE001 - surface Fido/network errors cleanly
        if _is_missing_dependency(exc):
            raise HTTPException(503, _SCI_INSTALL_HINT)
        raise HTTPException(502, f"Archive search failed: {type(exc).__name__}: {exc}")


@router.post("/source/find-latest", response_model=SearchResponse)
async def source_find_latest(req: SearchRequest) -> SearchResponse:
    """Walk back to the archive's data frontier and return the newest available
    records (for lagging archives such as SOHO/LASCO)."""
    import asyncio

    try:
        return await asyncio.to_thread(acquire.run_find_latest, req)
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    except Exception as exc:  # noqa: BLE001
        if _is_missing_dependency(exc):
            raise HTTPException(503, _SCI_INSTALL_HINT)
        raise HTTPException(502, f"Find-latest failed: {type(exc).__name__}: {exc}")


@router.post("/source/fetch-selected", response_model=JobStatusResponse)
async def source_fetch_selected(req: FetchSelectionRequest) -> JobStatusResponse:
    """Start a background download of the selected search rows into a session."""
    if req.source not in ("auto", "jsoc", "vso"):
        raise HTTPException(422, "source must be auto, jsoc or vso")
    if req.frame_size not in ("full", "bin2", "bin4", "cutout"):
        raise HTTPException(422, "frame_size must be full, bin2, bin4 or cutout")
    cutout = (req.cutout_x, req.cutout_y, req.cutout_w, req.cutout_h)
    job_id = job_manager.submit(
        acquire.fetch_selected_job,
        req.search_id, req.indices, req.source, req.frame_size, cutout,
    )
    job = job_manager.get(job_id)
    assert job is not None
    return _job_response(job)


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


class SessionExportRequest(BaseModel):
    """Bundle a session (frames + state) into a desktop-compatible .ecsolar."""
    session: str
    picks: list[dict] = []            # web height–time picks: {frame, px, py}
    display: dict = {}                # PlotParams snapshot to restore later


@router.post("/session/export")
async def session_export(req: SessionExportRequest) -> FileResponse:
    import asyncio

    try:
        path = await asyncio.to_thread(
            data.export_session_bundle, req.session, req.picks, req.display
        )
    except FileNotFoundError:
        raise HTTPException(404, "Analysis session not found")
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    headers = {"Content-Disposition": f'attachment; filename="{Path(path).name}"'}
    return FileResponse(path, media_type="application/zip", headers=headers)


@router.post("/session/import")
async def session_import(file: UploadFile = File(...)) -> dict:
    """Restore a .ecsolar bundle (from this dashboard or the desktop analyzer)."""
    import asyncio

    name = (file.filename or "").lower()
    if not name.endswith((".ecsolar", ".zip")):
        raise HTTPException(400, "Expected a .ecsolar session file")
    content = await file.read()
    try:
        result = await asyncio.to_thread(data.import_session_bundle, content)
    except Exception as exc:  # noqa: BLE001 - malformed bundles → clear 422
        raise HTTPException(422, f"Could not restore session: {exc}")
    return {
        "session": result["session"].model_dump(mode="json"),
        "picks": result["picks"],
        "display": result["display"],
    }


@router.get("/export/regions-csv")
async def export_regions_csv(
    session: str = Query(...),
    frame: int = Query(0),
    threshold_pct: float = Query(98.0, ge=50.0, le=100.0),
    min_area: int = Query(40, ge=1),
) -> FileResponse:
    """Bright-region detection table as CSV (ported detect_active_regions)."""
    try:
        path = data.regions_csv(session, frame, threshold_pct, min_area)
    except FileNotFoundError:
        raise HTTPException(404, "Analysis session or frame not found")
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    headers = {"Content-Disposition": f'attachment; filename="regions_{session[:8]}_{frame}.csv"'}
    return FileResponse(path, media_type="text/csv", headers=headers)


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
    nrgf: bool = False,
    grid_frame: str = "",
) -> PlotParams:
    if cmap not in COLORMAPS:
        raise HTTPException(422, f"cmap must be one of {COLORMAPS}")
    if scale not in SCALES:
        raise HTTPException(422, f"scale must be one of {SCALES}")
    if grid_frame not in analysis.GRID_FRAMES:
        raise HTTPException(422, f"grid_frame must be one of {analysis.GRID_FRAMES}")
    return PlotParams(
        cmap=cmap, scale=scale, clip_low=clip_low, clip_high=clip_high,
        vmin=vmin, vmax=vmax, crop=crop, bl_x=bl_x, bl_y=bl_y, tr_x=tr_x, tr_y=tr_y,
        draw_limb=draw_limb, draw_grid=draw_grid, colorbar=colorbar,
        nrgf=nrgf, grid_frame=grid_frame,
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
    nrgf: bool = Query(False),
    grid_frame: str = Query(""),
    download: bool = Query(False),
) -> FileResponse:
    params = _plot_params(
        cmap, scale, clip_low, clip_high, vmin, vmax,
        crop, bl_x, bl_y, tr_x, tr_y, draw_limb, draw_grid, colorbar,
        nrgf=nrgf, grid_frame=grid_frame,
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


@router.get("/render-bare")
async def render_bare(
    session: str = Query(...),
    frame: int = Query(0),
    mode: str = Query("plot", pattern="^(plot|running|base)$"),
    base_index: int = Query(0),
    cmap: str = Query("auto"),
    scale: str = Query("linear"),
    clip_low: float = Query(1.0),
    clip_high: float = Query(99.9),
    vmin: float | None = Query(None),
    vmax: float | None = Query(None),
    nrgf: bool = Query(False),
) -> FileResponse:
    """Exact-pixel PNG (1:1 with the data array, origin bottom-left) for the
    interactive canvas. No axes/colorbar — clicks map linearly to data pixels."""
    params = _plot_params(
        cmap, scale, clip_low, clip_high, vmin, vmax,
        False, 0.0, 0.0, 0.0, 0.0, False, False, True, nrgf=nrgf,
    )
    try:
        path = analysis.render_bare(session, frame, params, mode=mode, base_index=base_index)
    except FileNotFoundError:
        raise HTTPException(404, "Analysis session or frame not found")
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    return FileResponse(path, media_type="image/png")


@router.get("/frame-meta")
async def frame_meta(session: str = Query(...), frame: int = Query(0)) -> dict:
    """WCS/geometry for the interactive canvas (shape, Sun-centre pixel, plate
    scale, rotation matrix, apparent solar radius)."""
    try:
        return data.frame_wcs_meta(session, frame)
    except FileNotFoundError:
        raise HTTPException(404, "Analysis session or frame not found")
    except ValueError as exc:
        raise HTTPException(422, str(exc))


@router.get("/coord")
async def coord(
    session: str = Query(...),
    frame: int = Query(0),
    px: float = Query(...),
    py: float = Query(...),
    frame_key: str = Query("HGS"),
) -> dict:
    """Exact WCS readout for a data pixel (arcsec, R☉, PA, lon/lat, data value)."""
    if frame_key.upper() not in ("HGS", "HGC", "HCI"):
        raise HTTPException(422, "frame_key must be HGS, HGC or HCI")
    try:
        return data.coord_readout(session, frame, px, py, frame_key)
    except FileNotFoundError:
        raise HTTPException(404, "Analysis session or frame not found")
    except ValueError as exc:
        raise HTTPException(422, str(exc))


# ── measurements + region light curve (interactive canvas tools) ─────────────────


@router.get("/measure/ruler")
async def measure_ruler(
    session: str = Query(...),
    frame: int = Query(0),
    x1: float = Query(...), y1: float = Query(...),
    x2: float = Query(...), y2: float = Query(...),
) -> dict:
    """Two-point plane-of-sky distance (arcsec/R☉/km) + N→E position angle."""
    try:
        return measure.measure_ruler(session, frame, x1, y1, x2, y2)
    except FileNotFoundError:
        raise HTTPException(404, "Analysis session or frame not found")
    except ValueError as exc:
        raise HTTPException(422, str(exc))


@router.get("/measure/profile")
async def measure_profile(
    session: str = Query(...),
    frame: int = Query(0),
    x1: float = Query(...), y1: float = Query(...),
    x2: float = Query(...), y2: float = Query(...),
) -> dict:
    """Intensity profile along a segment (arcsec distance scale)."""
    try:
        return measure.measure_profile(session, frame, x1, y1, x2, y2)
    except FileNotFoundError:
        raise HTTPException(404, "Analysis session or frame not found")
    except ValueError as exc:
        raise HTTPException(422, str(exc))


@router.get("/measure/region")
async def measure_region(
    session: str = Query(...),
    frame: int = Query(0),
    x0: float = Query(...), y0: float = Query(...),
    x1: float = Query(...), y1: float = Query(...),
) -> dict:
    """Rectangle statistics + intensity-weighted centroid (px + arcsec)."""
    try:
        return measure.measure_region(session, frame, x0, y0, x1, y1)
    except FileNotFoundError:
        raise HTTPException(404, "Analysis session or frame not found")
    except ValueError as exc:
        raise HTTPException(422, str(exc))


@router.post("/height-time")
async def height_time(req: HeightTimeRequest) -> dict:
    """CME height–time fit: leading-edge picks → speed (km/s), acceleration
    (km/s²), per-segment speeds (ported coronagraph.fit_height_time)."""
    if not req.picks:
        raise HTTPException(422, "At least one pick is required.")
    try:
        return measure.height_time(req.session, req.picks)
    except FileNotFoundError:
        raise HTTPException(404, "Analysis session or frame not found")
    except ValueError as exc:
        raise HTTPException(422, str(exc))


@router.get("/lightcurve")
async def lightcurve(
    session: str = Query(...),
    x0: float = Query(...), y0: float = Query(...),
    x1: float = Query(...), y1: float = Query(...),
    statistic: str = Query("mean", pattern="^(mean|sum)$"),
    radio_start: datetime | None = Query(None),
    radio_end: datetime | None = Query(None),
) -> dict:
    """ROI intensity vs time (DN/s) across all frames, with optional
    radio-burst-window timing (EUV-peak-minus-radio-onset lag)."""
    import asyncio

    try:
        return await asyncio.to_thread(
            measure.region_lightcurve, session, x0, y0, x1, y1, statistic, radio_start, radio_end
        )
    except FileNotFoundError:
        raise HTTPException(404, "Analysis session not found")
    except ValueError as exc:
        raise HTTPException(422, str(exc))


@router.get("/export/fits")
async def export_fits(
    session: str = Query(...),
    frame: int = Query(0),
    crop: bool = Query(False),
    bl_x: float = Query(0.0),
    bl_y: float = Query(0.0),
    tr_x: float = Query(0.0),
    tr_y: float = Query(0.0),
) -> FileResponse:
    """Download one frame as FITS (optionally cropped; WCS kept correct)."""
    params = _plot_params(
        "auto", "linear", 1.0, 99.9, None, None,
        crop, bl_x, bl_y, tr_x, tr_y, False, False, True,
    )
    try:
        path = analysis.export_fits(session, frame, params)
    except FileNotFoundError:
        raise HTTPException(404, "Analysis session or frame not found")
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    headers = {
        "Content-Disposition": f'attachment; filename="solar_{session[:8]}_frame{frame}{"_crop" if crop else ""}.fits"'
    }
    return FileResponse(path, media_type="application/fits", headers=headers)


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


# ── specialized science: J-map, HMI vector field, compare viewpoint ─────────────


@router.post("/jmap", response_model=JobStatusResponse)
async def jmap(req: JMapRequest) -> JobStatusResponse:
    """Start a background J-map build (time–elongation map along a slit)."""
    if req.background not in ("median", "previous"):
        raise HTTPException(422, "background must be median or previous")
    job_id = job_manager.submit(
        science.jmap_job, req.session, req.pa_deg, req.background, max(0, int(req.half_width))
    )
    job = job_manager.get(job_id)
    assert job is not None
    return _job_response(job)


@router.post("/vector-field/prepare", response_model=JobStatusResponse)
async def vector_prepare(req: VectorPrepareRequest) -> JobStatusResponse:
    """Fetch + assemble hmi.B_720s vector segments for a session (background)."""
    job_id = job_manager.submit(science.vector_prepare_job, req.session, req.frame)
    job = job_manager.get(job_id)
    assert job is not None
    return _job_response(job)


@router.get("/vector-field")
async def vector_field(
    session: str = Query(...),
    frame: int = Query(0),
    arrows: bool = Query(True),
    streamlines: bool = Query(False),
    magnitude: bool = Query(False),
    grid_step: int = Query(64, ge=8, le=512),
    min_gauss: float = Query(200.0, ge=0.0),
    cmap: str = Query("auto"),
    scale: str = Query("linear"),
    clip_low: float = Query(1.0),
    clip_high: float = Query(99.9),
    draw_limb: bool = Query(False),
    colorbar: bool = Query(True),
    download: bool = Query(False),
) -> FileResponse:
    """HMI frame + magnetic vector-field overlay (red = +Bz, blue = −Bz)."""
    params = _plot_params(
        cmap, scale, clip_low, clip_high, None, None,
        False, 0.0, 0.0, 0.0, 0.0, draw_limb, False, colorbar,
    )
    dpi = analysis.EXPORT_DPI if download else analysis.RENDER_DPI
    try:
        path = science.render_vector_field(
            session, frame, params,
            show_arrows=arrows, show_streamlines=streamlines, show_magnitude=magnitude,
            grid_step_px=grid_step, min_gauss=min_gauss, dpi=dpi,
        )
    except FileNotFoundError:
        raise HTTPException(404, "Analysis session or frame not found")
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    except Exception as exc:  # noqa: BLE001 - vector assembly errors → clear 422
        raise HTTPException(422, f"Vector-field render failed: {exc}")
    headers = {}
    if download:
        headers["Content-Disposition"] = f'attachment; filename="hmi_vector_{session[:8]}_{frame}.png"'
    return FileResponse(path, media_type="image/png", headers=headers)


@router.get("/compare-viewpoint/info")
async def compare_viewpoint_info(
    session: str = Query(...),
    frame: int = Query(0),
    other: str = Query(...),
    other_frame: int = Query(0),
) -> dict:
    """Observer separation + labels for a two-viewpoint pair."""
    try:
        return science.compare_info(session, frame, other, other_frame)
    except FileNotFoundError:
        raise HTTPException(404, "One of the sessions/frames was not found")
    except ValueError as exc:
        raise HTTPException(422, str(exc))


@router.get("/compare-viewpoint")
async def compare_viewpoint(
    session: str = Query(...),
    frame: int = Query(0),
    other: str = Query(...),
    other_frame: int = Query(0),
    view: str = Query("primary", pattern="^(primary|reprojected)$"),
    cmap: str = Query("auto"),
    scale: str = Query("linear"),
    clip_low: float = Query(1.0),
    clip_high: float = Query(99.9),
    draw_limb: bool = Query(False),
    colorbar: bool = Query(True),
) -> FileResponse:
    """One side of a two-viewpoint blink: the primary frame, or the other
    session's frame reprojected onto the primary WCS/observer."""
    import asyncio

    params = _plot_params(
        cmap, scale, clip_low, clip_high, None, None,
        False, 0.0, 0.0, 0.0, 0.0, draw_limb, False, colorbar,
    )
    try:
        path = await asyncio.to_thread(
            science.render_compare, session, frame, other, other_frame, view, params
        )
    except FileNotFoundError:
        raise HTTPException(404, "One of the sessions/frames was not found")
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    except Exception as exc:  # noqa: BLE001 - reprojection errors → clear 422
        raise HTTPException(422, f"Reprojection failed: {exc}")
    return FileResponse(path, media_type="image/png")


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
