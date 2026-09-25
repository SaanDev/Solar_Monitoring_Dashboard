from datetime import datetime

from fastapi import APIRouter, Query, HTTPException, Response

from app.schemas.solar_image_schema import (
    SolarImageResponse,
    LascoMovieResponse,
    SolarArchiveResponse,
)
from app.services.solar_image_service import get_latest_solar_images, get_solar_images
from app.services.lasco_service import get_lasco_latest, get_lasco_movie
from app.services.solar_archive_service import (
    get_archive_images,
    fetch_screenshot_png,
    fetch_jp2,
    fetch_fts,
)

router = APIRouter(prefix="/api", tags=["solar"])


def _parse_date(value: str):
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="date must be YYYY-MM-DD") from exc


@router.get("/solar/images/latest", response_model=list[SolarImageResponse])
async def solar_images_latest() -> list[SolarImageResponse]:
    return await get_latest_solar_images()


@router.get("/solar/images", response_model=list[SolarImageResponse])
async def solar_images(
    source: str | None = Query(None),
    instrument: str | None = Query(None),
    wavelength: str | None = Query(None),
) -> list[SolarImageResponse]:
    return await get_solar_images(source, instrument, wavelength)


@router.get("/soho/lasco/latest", response_model=SolarImageResponse)
async def lasco_latest(camera: str = Query("C2")) -> SolarImageResponse:
    img = await get_lasco_latest(camera)
    if img is None:
        raise HTTPException(status_code=503, detail=f"LASCO {camera} not available")
    return img


@router.get("/soho/lasco/movie", response_model=LascoMovieResponse)
async def lasco_movie(camera: str = Query("C2")) -> LascoMovieResponse:
    movie = await get_lasco_movie(camera)
    if movie is None:
        raise HTTPException(status_code=503, detail=f"LASCO {camera} movie not available")
    return movie


# ─── Archive: historical full-disk + coronagraph images by date (Helioviewer) ──


@router.get("/solar/archive/images", response_model=SolarArchiveResponse)
async def solar_archive_images(
    date: str = Query(..., description="UTC date YYYY-MM-DD"),
    time: str = Query("12:00", description="UTC time HH:MM"),
    events: bool = Query(False, description="Overlay NOAA SWPC active regions"),
    latest: bool = Query(False, description="Show the newest frame available on the day"),
) -> SolarArchiveResponse:
    return await get_archive_images(_parse_date(date), time, events, latest)


@router.get("/solar/archive/image")
async def solar_archive_image(
    date: str = Query(...),
    id: str = Query(..., description="Catalog image id, e.g. aia171"),
    time: str = Query("12:00"),
    events: bool = Query(False),
    download: bool = Query(False),
) -> Response:
    content = await fetch_screenshot_png(_parse_date(date), time, id, events)
    if content is None:
        raise HTTPException(status_code=404, detail=f"Unknown solar image id: {id}")
    headers = {}
    if download:
        suffix = "_AR" if events else ""
        name = f"{id}_{date}_{time.replace(':', '')}{suffix}.png"
        headers["Content-Disposition"] = f'attachment; filename="{name}"'
    return Response(content=content, media_type="image/png", headers=headers)


@router.get("/solar/archive/jp2")
async def solar_archive_jp2(
    date: str = Query(...),
    id: str = Query(..., description="Catalog image id, e.g. aia171"),
    time: str = Query("12:00"),
    download: bool = Query(False),
) -> Response:
    result = await fetch_jp2(_parse_date(date), time, id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Unknown solar image id: {id}")
    content, fname = result
    headers = {"Content-Disposition": f'attachment; filename="{fname}"'} if download else {}
    return Response(content=content, media_type="image/jp2", headers=headers)


@router.get("/solar/archive/fits")
async def solar_archive_fits(
    date: str = Query(...),
    id: str = Query(..., description="Catalog image id, e.g. aia171"),
    time: str = Query("12:00"),
    download: bool = Query(False),
) -> Response:
    """Download the raw science FITS (AIA/HMI synoptic), streamed from JSOC."""
    result = await fetch_fts(_parse_date(date), time, id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"No FITS available for {id} on {date}")
    content, fname = result
    headers = {"Content-Disposition": f'attachment; filename="{fname}"'} if download else {}
    return Response(content=content, media_type="application/fits", headers=headers)
