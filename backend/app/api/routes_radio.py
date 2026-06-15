import shutil
import tempfile
from pathlib import Path

from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import FileResponse

from app.schemas.radio_schema import (
    RadioStationResponse,
    RadioSpectrumResponse,
    BurstEventsResponse,
    BurstSpectrumResponse,
)
from app.services.ecallisto_service import (
    list_stations,
    process_fits_file,
    get_sri_lanka_live,
    get_latest_burst_events,
    get_burst_spectrum,
)
from app.config import settings

router = APIRouter(prefix="/api/radio", tags=["radio"])


@router.get("/stations", response_model=list[RadioStationResponse])
async def get_stations() -> list[RadioStationResponse]:
    return list_stations()


@router.get("/sri-lanka/live", response_model=RadioSpectrumResponse)
async def sri_lanka_live() -> RadioSpectrumResponse:
    result = await get_sri_lanka_live()
    if result is None:
        raise HTTPException(status_code=503, detail="No recent SRI-Lanka data available")
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
async def get_spectrum_image(filename: str) -> FileResponse:
    path = Path(settings.spectra_dir) / filename
    if not path.exists():
        raise HTTPException(status_code=404, detail="Spectrum image not found")
    return FileResponse(path, media_type="image/png")
