import shutil
import tempfile
from datetime import date as date_cls, datetime
from pathlib import Path

from datetime import timedelta, timezone

from fastapi import APIRouter, UploadFile, File, HTTPException, Query, Response, Depends
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.repositories.radio_detection_repo import detections_for_range
from app.schemas.radio_schema import (
    RadioStationResponse,
    RadioSpectrumResponse,
    RadioLiveStationsResponse,
    RadioArchiveStationsResponse,
    RadioArchiveFilesResponse,
    BurstEventsResponse,
    BurstSpectrumResponse,
    RadioBurstDetectionResponse,
    RadioBurstDetectionsResponse,
    BurstPredictionRequest,
    BurstPredictionJob,
    BurstPredictionResult,
    BurstScorecardResponse,
    BinaryModelSelection,
    ModelsResponse,
    OfficialBurstRangeResponse,
    BackfillDayCoverage,
    BackfillJob,
    BackfillRequest,
    BackfillStatusResponse,
)
from app.ml import registry
from app.services import burst_predictor_service as predictor
from app.services import model_settings_service as model_settings
from app.services import radio_backfill_service as backfill
from app.services.burst_scorecard_service import get_official_bursts_range, get_scorecard
from app.services.ecallisto_service import (
    list_stations,
    process_fits_file,
    get_sri_lanka_live,
    get_live_stations,
    get_live_spectrum,
    get_latest_burst_events,
    get_burst_spectrum,
    list_archive_stations,
    list_archive_files,
    get_archive_spectrum,
    get_archive_spectrum_at,
    get_archive_fits,
    get_burst_events_for_date,
    get_burst_spectrum_for_date,
)
from app.config import settings

router = APIRouter(prefix="/api/radio", tags=["radio"])


def _parse_date(value: str) -> date_cls:
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="date must be YYYY-MM-DD") from exc


@router.get("/stations", response_model=list[RadioStationResponse])
async def get_stations() -> list[RadioStationResponse]:
    return list_stations()


@router.get("/sri-lanka/live", response_model=RadioSpectrumResponse)
async def sri_lanka_live() -> RadioSpectrumResponse:
    result = await get_sri_lanka_live()
    if result is None:
        raise HTTPException(status_code=503, detail="No recent SRI-Lanka data available")
    return result


@router.get("/live/stations", response_model=RadioLiveStationsResponse)
async def live_stations() -> RadioLiveStationsResponse:
    """Stations + focus codes available on the most recent day with data."""
    return await get_live_stations()


@router.get("/live/spectrum", response_model=RadioSpectrumResponse)
async def live_spectrum(
    station: str = Query(...),
    focus: str | None = Query(None, description="Focus code; latest of any focus if omitted"),
) -> RadioSpectrumResponse:
    """Latest available dynamic spectrum for a station (and optional focus code)."""
    result = await get_live_spectrum(station, focus)
    if result is None:
        raise HTTPException(status_code=404, detail=f"No recent data for {station}")
    return result


@router.get("/bursts/latest", response_model=BurstEventsResponse)
async def bursts_latest() -> BurstEventsResponse:
    return await get_latest_burst_events()


@router.get("/bursts/range", response_model=OfficialBurstRangeResponse)
async def bursts_range(
    start: str = Query(..., description="UTC date YYYY-MM-DD (inclusive)"),
    end: str = Query(..., description="UTC date YYYY-MM-DD (inclusive)"),
) -> OfficialBurstRangeResponse:
    """Official e-CALLISTO burst-list events over a date range (max 31 days) —
    backs the Timeline page's 'Radio · Official' lane."""
    first, last = _parse_date(start), _parse_date(end)
    if last < first:
        raise HTTPException(status_code=400, detail="end is before start")
    if (last - first).days > 31:
        raise HTTPException(status_code=400, detail="range is limited to 31 days")
    return await get_official_bursts_range(first, last)


@router.get("/bursts/detections", response_model=RadioBurstDetectionsResponse)
async def burst_detections(
    date: str = Query(..., description="UTC date YYYY-MM-DD"),
    db: AsyncSession = Depends(get_db),
) -> RadioBurstDetectionsResponse:
    """Per-file ML burst-classifier results for a UTC date (audit / inspection)."""
    day = _parse_date(date)
    start = datetime(day.year, day.month, day.day, tzinfo=timezone.utc)
    rows = await detections_for_range(db, start, start + timedelta(days=1))
    detections = [
        RadioBurstDetectionResponse(
            filename=r["filename"],
            station=r["station"],
            start_time=r["start_time"],
            probability=r["probability"],
            predicted_label=r["predicted_label"],
            alert_level=r["alert_level"],
            model_id=r.get("model_id") or "",
            burst_type=r.get("burst_type"),
            type_confidence=r.get("type_confidence"),
        )
        for r in rows
    ]
    burst_count = sum(1 for d in detections if d.predicted_label == "Burst")
    return RadioBurstDetectionsResponse(
        date=day.isoformat(),
        count=len(detections),
        burst_count=burst_count,
        detections=detections,
    )


@router.get("/models", response_model=ModelsResponse)
async def list_models() -> ModelsResponse:
    """The burst classifiers this backend can run, for the model selector.

    ``available`` reflects whether each checkpoint is actually on disk (and not
    an unpulled Git LFS pointer), so the UI can disable a model up front rather
    than surfacing a mid-scan failure.

    Declared before ``/predict/{job_id}`` for consistency with the other fixed
    paths in this router.
    """
    return model_settings.describe_models()


@router.put("/models/default", response_model=ModelsResponse)
async def select_default_model(
    payload: BinaryModelSelection, db: AsyncSession = Depends(get_db)
) -> ModelsResponse:
    """Choose the binary classifier the **automatic** burst scan runs.

    Persisted, so it survives a restart, and applied immediately: the next
    scheduled pass re-scores the recent window with the new model (detections are
    deduped per model) and rebuilds the burst events from it. The Burst Detector
    page's per-run picker is unaffected — this only moves its default.
    """
    try:
        return await model_settings.select_binary_model(db, payload.model_id)
    except registry.UnknownModelError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except model_settings.ModelUnavailableError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/backfill", response_model=BackfillStatusResponse)
async def backfill_status(
    days: int = Query(30, ge=1, le=365, description="Days of coverage to report"),
    db: AsyncSession = Depends(get_db),
) -> BackfillStatusResponse:
    """Per-day archive coverage plus the current (or last) catch-up run.

    ``state`` per day: "done" once the day is scored, "partial" while segments are
    still missing, "unknown" for a day the catch-up has never inspected. Today is
    always partial by design — its most recent hours belong to the live scan.
    """
    rows = await backfill.coverage(db, days)
    job = backfill.current_job()
    return BackfillStatusResponse(
        enabled=settings.radio_burst_enabled and settings.radio_burst_backfill_enabled,
        running=backfill.is_running(),
        auto_window_days=settings.radio_burst_backfill_max_days,
        live_window_hours=settings.radio_burst_max_age_hours,
        job=BackfillJob(**job) if job else None,
        coverage=[BackfillDayCoverage(**r) for r in rows],
    )


@router.post("/backfill", response_model=BackfillJob)
async def start_backfill(req: BackfillRequest) -> BackfillJob:
    """Run the ML burst detection over days the dashboard missed.

    Defaults to the automatic window (the last ``RADIO_BURST_BACKFILL_MAX_DAYS``
    days); pass ``start``/``end`` to reach further back than the automatic pass
    ever will. Returns immediately — poll ``GET /api/radio/backfill`` for progress.
    """
    today = datetime.now(timezone.utc).date()
    last = _parse_date(req.end) if req.end else today
    first = (
        _parse_date(req.start)
        if req.start
        else last - timedelta(days=max(0, settings.radio_burst_backfill_max_days - 1))
    )
    if last < first:
        raise HTTPException(status_code=400, detail="end is before start")
    if first > today:
        raise HTTPException(status_code=400, detail="start is in the future")
    last = min(last, today)
    if (last - first).days > 365:
        raise HTTPException(status_code=400, detail="range is limited to 366 days")
    try:
        job = backfill.start(first, last, force=req.force, trigger="manual")
    except backfill.BackfillBusyError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return BackfillJob(**job)


@router.post("/backfill/cancel", response_model=BackfillJob)
async def cancel_backfill() -> BackfillJob:
    """Stop the running catch-up after the chunk in flight.

    Everything already scored stays: the run is resumable, so restarting it picks
    up from the archive listing minus what is stored.
    """
    if not backfill.cancel():
        raise HTTPException(status_code=409, detail="no catch-up run in progress")
    job = backfill.current_job()
    return BackfillJob(**job)  # type: ignore[arg-type]  # cancel() implies a job


@router.post("/predict", response_model=BurstPredictionJob)
async def start_prediction(req: BurstPredictionRequest) -> BurstPredictionJob:
    """Kick off a background model run over a day's e-CALLISTO segments.

    Poll ``GET /api/radio/predict/{job_id}`` for progress and the result.
    """
    day = _parse_date(req.date)
    if day > datetime.now(timezone.utc).date():
        raise HTTPException(status_code=400, detail="date is in the future")
    stations = [s for s in (req.stations or []) if s]
    try:
        job_id = predictor.start_prediction(
            day, stations, req.raw, model_id=req.model, classify_types=req.classify_types
        )
    except registry.UnknownModelError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    job = predictor.get_job(job_id)
    return BurstPredictionJob(
        **{
            k: job[k]
            for k in (
                "job_id", "status", "scanned", "total", "date", "stations",
                "model_id", "classify_types", "error",
            )
        }
    )


@router.get("/predict/stored", response_model=BurstPredictionResult)
async def prediction_stored(
    date: str = Query(..., description="UTC date YYYY-MM-DD"),
    raw: bool = Query(
        False,
        description="True = raw model detections (skip corroboration); "
        "False = event-selection criteria (default).",
    ),
    db: AsyncSession = Depends(get_db),
) -> BurstPredictionResult:
    """Burst-prediction result assembled from already-stored real-time detections
    for a date (no re-scoring) — backs the 'view bursts' link from an alert.

    The model is taken from the stored rows themselves, so a day scanned by an
    earlier model is scored against *that* model's threshold.

    Declared before ``/predict/{job_id}`` so that path param doesn't capture it.
    """
    day = _parse_date(date)
    start = datetime(day.year, day.month, day.day, tzinfo=timezone.utc)
    rows = await detections_for_range(db, start, start + timedelta(days=1))
    result = await predictor.assemble_result(rows, day, raw=raw)
    return BurstPredictionResult(**result)


@router.get("/predict/scorecard", response_model=BurstScorecardResponse)
async def prediction_scorecard(
    days: int = Query(30, ge=7, le=60),
    db: AsyncSession = Depends(get_db),
) -> BurstScorecardResponse:
    """Model performance over the trailing window: stored real-time detections
    vs. the official burst list, per day + totals (recall / precision).

    Declared before ``/predict/{job_id}`` so that path param doesn't capture it.
    """
    return await get_scorecard(db, days)


@router.get("/predict/{job_id}", response_model=BurstPredictionJob)
async def prediction_status(
    job_id: str,
    raw: bool | None = Query(
        None,
        description="Override the event-selection mode for assembling the result: "
        "true = raw model detections (skip corroboration), false = criteria. "
        "Defaults to the mode the job was started with. Re-assembles from the "
        "already-scored rows, so toggling never re-scores.",
    ),
) -> BurstPredictionJob:
    """Progress for a prediction job; includes the full result once done."""
    job = predictor.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="prediction job not found")
    result = None
    if job["status"] == "done":
        day = _parse_date(job["date"])
        effective_raw = job.get("raw", False) if raw is None else raw
        result = BurstPredictionResult(
            **await predictor.assemble_result(
                job["rows"],
                day,
                job["stations"],
                effective_raw,
                model_id=job.get("model_id"),
                classify_types=job.get("classify_types"),
            )
        )
    return BurstPredictionJob(
        job_id=job["job_id"],
        status=job["status"],
        scanned=job["scanned"],
        total=job["total"],
        date=job["date"],
        stations=job["stations"],
        model_id=job.get("model_id", ""),
        classify_types=bool(job.get("classify_types", False)),
        error=job["error"],
        result=result,
    )


@router.get("/bursts/{index}/spectrum", response_model=BurstSpectrumResponse)
async def burst_spectrum(index: int) -> BurstSpectrumResponse:
    result = await get_burst_spectrum(index)
    if result is None:
        raise HTTPException(
            status_code=404, detail=f"No FITS spectrum available for burst {index}"
        )
    return result


# ─── Archive (browse by date + station) ─────────────────────────────────────


@router.get("/archive/stations", response_model=RadioArchiveStationsResponse)
async def archive_stations(date: str = Query(..., description="UTC date YYYY-MM-DD")):
    return await list_archive_stations(_parse_date(date))


@router.get("/archive/files", response_model=RadioArchiveFilesResponse)
async def archive_files(
    date: str = Query(..., description="UTC date YYYY-MM-DD"),
    station: str = Query(...),
):
    return await list_archive_files(_parse_date(date), station)


@router.get("/archive/spectrum", response_model=RadioSpectrumResponse)
async def archive_spectrum(
    date: str = Query(..., description="UTC date YYYY-MM-DD"),
    station: str = Query(...),
    filename: str | None = Query(None, description="Specific segment; latest of the day if omitted"),
) -> RadioSpectrumResponse:
    result = await get_archive_spectrum(_parse_date(date), station, filename)
    if result is None:
        raise HTTPException(
            status_code=404, detail=f"No spectrum available for {station} on {date}"
        )
    return result


@router.get("/archive/spectrum-at", response_model=RadioSpectrumResponse)
async def archive_spectrum_at(
    date: str = Query(..., description="UTC date YYYY-MM-DD"),
    station: str = Query(...),
    time: str = Query(..., description="HH:MM UTC inside the event window"),
) -> RadioSpectrumResponse:
    """Dynamic spectrum for the segment covering a given time — used to preview an
    official burst-list event's station (which has a time, not a filename)."""
    result = await get_archive_spectrum_at(_parse_date(date), station, time)
    if result is None:
        raise HTTPException(
            status_code=404, detail=f"No spectrum for {station} at {time} on {date}"
        )
    return result


@router.get("/archive/fits")
async def archive_fits(
    date: str = Query(..., description="UTC date YYYY-MM-DD"),
    station: str = Query(...),
    filename: str = Query(..., description="Archive FITS filename"),
) -> Response:
    """Download the raw .fit.gz, streamed from the e-CALLISTO archive."""
    result = await get_archive_fits(_parse_date(date), station, filename)
    if result is None:
        raise HTTPException(status_code=404, detail=f"FITS file not found: {filename}")
    content, name = result
    return Response(
        content=content,
        media_type="application/gzip",
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )


@router.get("/bursts", response_model=BurstEventsResponse)
async def bursts_by_date(date: str = Query(..., description="UTC date YYYY-MM-DD")):
    return await get_burst_events_for_date(_parse_date(date))


@router.get("/bursts/spectrum", response_model=BurstSpectrumResponse)
async def burst_spectrum_by_date(
    date: str = Query(..., description="UTC date YYYY-MM-DD"),
    index: int = Query(..., ge=0),
) -> BurstSpectrumResponse:
    result = await get_burst_spectrum_for_date(_parse_date(date), index)
    if result is None:
        raise HTTPException(
            status_code=404, detail=f"No FITS spectrum available for burst {index} on {date}"
        )
    return result


@router.post("/ecallisto/process", response_model=RadioSpectrumResponse)
async def process_ecallisto(
    file: UploadFile = File(...),
    station: str = "UNKNOWN",
) -> RadioSpectrumResponse:
    if not file.filename or not file.filename.lower().endswith((".fit", ".fits")):
        raise HTTPException(status_code=400, detail="File must be a FITS file (.fit or .fits)")

    with tempfile.NamedTemporaryFile(suffix=".fits", delete=False) as tmp:
        shutil.copyfileobj(file.file, tmp)
        tmp_path = Path(tmp.name)

    try:
        result = process_fits_file(tmp_path, station=station)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"FITS processing failed: {exc}") from exc
    finally:
        tmp_path.unlink(missing_ok=True)

    return result


@router.get("/spectra/{filename}")
async def get_spectrum_image(
    filename: str,
    download: bool = Query(False, description="Serve as an attachment download"),
) -> FileResponse:
    base = Path(settings.spectra_dir).resolve()
    path = (base / filename).resolve()
    # Containment check: never serve a path outside the spectra directory.
    try:
        path.relative_to(base)
    except ValueError:
        raise HTTPException(status_code=404, detail="Spectrum image not found")
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Spectrum image not found")
    # Passing filename= sets Content-Disposition: attachment for a real download.
    return FileResponse(
        path, media_type="image/png", filename=filename if download else None
    )
