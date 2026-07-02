"""Latest full-disk solar images.

Uses official near-real-time browse images, which are full-disk, fresh
(~10-15 min cadence) and require no server-side rendering:
    SDO/AIA, SDO/HMI : https://sdo.gsfc.nasa.gov/assets/img/latest/
    GOES/SUVI        : https://services.swpc.noaa.gov/images/animations/suvi/
Each image's observation time is taken from the HTTP Last-Modified header,
so the timestamp stays consistent with the displayed frame.
"""
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import asyncio

import httpx

from app.schemas.solar_image_schema import SolarImageResponse

_SDO_BASE = "https://sdo.gsfc.nasa.gov/assets/img/latest"
_SUVI_BASE = "https://services.swpc.noaa.gov/images/animations/suvi/primary"


@dataclass(frozen=True)
class _Source:
    id: str
    source: str
    instrument: str
    wavelength: str       # filter key, e.g. "171", "continuum", "195"
    label: str            # human label, e.g. "AIA 171 Å"
    thumb_url: str
    full_url: str


def _sdo(id_: str, instrument: str, wavelength: str, label: str, code: str) -> _Source:
    return _Source(
        id=id_,
        source="SDO",
        instrument=instrument,
        wavelength=wavelength,
        label=label,
        thumb_url=f"{_SDO_BASE}/latest_512_{code}.jpg",
        full_url=f"{_SDO_BASE}/latest_2048_{code}.jpg",
    )


# Display order matches the dashboard gallery.
CATALOG: list[_Source] = [
    _sdo("aia171", "AIA", "171", "AIA 171 Å", "0171"),
    _sdo("aia193", "AIA", "193", "AIA 193 Å", "0193"),
    _sdo("aia211", "AIA", "211", "AIA 211 Å", "0211"),
    _sdo("aia304", "AIA", "304", "AIA 304 Å", "0304"),
    _sdo("aia131", "AIA", "131", "AIA 131 Å", "0131"),
    _sdo("aia335", "AIA", "335", "AIA 335 Å", "0335"),
    _sdo("hmiic", "HMI", "continuum", "HMI Continuum", "HMIIC"),
    _sdo("hmib", "HMI", "magnetogram", "HMI Magnetogram", "HMIB"),
    _Source(
        id="suvi195",
        source="GOES",
        instrument="SUVI",
        wavelength="195",
        label="SUVI 195 Å",
        thumb_url=f"{_SUVI_BASE}/195/latest.png",
        full_url=f"{_SUVI_BASE}/195/latest.png",
    ),
]


async def _observation_time(client: httpx.AsyncClient, url: str) -> datetime:
    """Read the frame time from the image's Last-Modified header (UTC)."""
    try:
        r = await client.head(url, timeout=10, follow_redirects=True)
        lm = r.headers.get("last-modified")
        if lm:
            return parsedate_to_datetime(lm).astimezone(timezone.utc)
    except Exception:
        pass
    return datetime.now(timezone.utc)


def _with_cache_bust(url: str, ts: datetime) -> str:
    return f"{url}?ts={int(ts.timestamp())}"


async def _build(client: httpx.AsyncClient, src: _Source) -> SolarImageResponse:
    ts = await _observation_time(client, src.thumb_url)
    return SolarImageResponse(
        id=src.id,
        source=src.source,
        instrument=src.instrument,
        wavelength=src.label,
        timestamp=ts,
        thumbnail_url=_with_cache_bust(src.thumb_url, ts),
        full_url=_with_cache_bust(src.full_url, ts),
    )


async def get_latest_solar_images() -> list[SolarImageResponse]:
    async with httpx.AsyncClient() as client:
        return await asyncio.gather(*(_build(client, s) for s in CATALOG))


async def get_solar_images(
    source: str | None, instrument: str | None, wavelength: str | None
) -> list[SolarImageResponse]:
    matches = [
        s
        for s in CATALOG
        if (source is None or s.source.lower() == source.lower())
        and (instrument is None or s.instrument.lower() == instrument.lower())
        and (wavelength is None or s.wavelength.lower() == wavelength.lower())
    ]
    async with httpx.AsyncClient() as client:
        return await asyncio.gather(*(_build(client, s) for s in matches))
