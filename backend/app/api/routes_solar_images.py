from fastapi import APIRouter, Query, HTTPException

from app.schemas.solar_image_schema import SolarImageResponse, LascoMovieResponse
from app.services.solar_image_service import get_latest_solar_images, get_solar_images
from app.services.lasco_service import get_lasco_latest, get_lasco_movie

router = APIRouter(prefix="/api", tags=["solar"])


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
