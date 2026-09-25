"""Latest SOHO/LASCO C2 and C3 coronagraph images.

Uses SOHO's near-real-time browse images:
https://soho.nascom.nasa.gov/data/realtime/{c2,c3}/512/latest.jpg
Frame time comes from the HTTP Last-Modified header.
"""
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

import httpx

from app.schemas.solar_image_schema import SolarImageResponse, LascoMovieResponse

_SOHO_BASE = "https://soho.nascom.nasa.gov/data/realtime"
_SOHO_LATEST = "https://soho.nascom.nasa.gov/data/LATEST"
_CAMERAS = {"C2", "C3"}

# SOHO's ready-made rolling "latest" movies (last few days of frames).
_MOVIE_URLS = {
    "C2": f"{_SOHO_LATEST}/current_c2.mp4",
    "C3": f"{_SOHO_LATEST}/current_c3.mp4",
}


async def get_lasco_latest(camera: str) -> SolarImageResponse | None:
    camera = camera.upper()
    if camera not in _CAMERAS:
        return None

    cam = camera.lower()
    thumb = f"{_SOHO_BASE}/{cam}/512/latest.jpg"
    full = f"{_SOHO_BASE}/{cam}/1024/latest.jpg"

    ts = datetime.now(timezone.utc)
    async with httpx.AsyncClient() as client:
        try:
            r = await client.head(thumb, timeout=10, follow_redirects=True)
            if r.status_code != 200:
                return None
            lm = r.headers.get("last-modified")
            if lm:
                ts = parsedate_to_datetime(lm).astimezone(timezone.utc)
        except Exception:
            return None

    bust = int(ts.timestamp())
    return SolarImageResponse(
        id=f"lasco-{cam}",
        source="SOHO",
        instrument=f"LASCO {camera}",
        wavelength="white-light",
        timestamp=ts,
        thumbnail_url=f"{thumb}?ts={bust}",
        full_url=f"{full}?ts={bust}",
    )


async def get_lasco_movie(camera: str) -> LascoMovieResponse | None:
    camera = camera.upper()
    url = _MOVIE_URLS.get(camera)
    if url is None:
        return None

    ts = datetime.now(timezone.utc)
    async with httpx.AsyncClient() as client:
        try:
            r = await client.head(url, timeout=15, follow_redirects=True)
            if r.status_code != 200:
                return None
            lm = r.headers.get("last-modified")
            if lm:
                ts = parsedate_to_datetime(lm).astimezone(timezone.utc)
        except Exception:
            return None

    return LascoMovieResponse(camera=camera, url=url, timestamp=ts)
