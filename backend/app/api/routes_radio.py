import shutil
import tempfile
from datetime import date as date_cls, datetime
from pathlib import Path

from fastapi import APIRouter, UploadFile, File, HTTPException, Query, Response
from fastapi.responses import FileResponse

from app.schemas.radio_schema import (
    RadioStationResponse,
    RadioSpectrumResponse,
    RadioLiveStationsResponse,
    RadioArchiveStationsResponse,
    RadioArchiveFilesResponse,
    BurstEventsResponse,
    BurstSpectrumResponse,
)
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
