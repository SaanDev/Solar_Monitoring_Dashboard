"""Latest full-disk solar images.

Uses official near-real-time quick-look images, which are full-disk, fresh
(~10-15 min cadence) and require no server-side rendering:
    SDO/AIA, SDO/HMI : newest of SDO's browse feeds / JSOC's HMI quick-looks
                       (see app.services.sdo_latest)
    GOES/SUVI        : https://services.swpc.noaa.gov/images/animations/suvi/
Each image's timestamp is its observation time — from the frame's filename or
JSOC's time manifest for SDO, the HTTP Last-Modified header for SUVI — so it
stays consistent with the displayed frame.
"""
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import asyncio

import httpx

from app.schemas.solar_image_schema import SolarImageResponse
from app.services.sdo_latest import latest_sdo_frames

_SUVI_BASE = "https://services.swpc.noaa.gov/images/animations/suvi/primary"


@dataclass(frozen=True)
class _Source:
    id: str
    source: str
    instrument: str
    wavelength: str       # filter key, e.g. "171", "continuum", "195"
    label: str            # human label, e.g. "AIA 171 Å"
    sdo_code: str | None = None  # SDO browse code; frame resolved per request
    url: str | None = None       # fixed-name image (thumb = full), timed by Last-Modified


def _sdo(id_: str, instrument: str, wavelength: str, label: str, code: str) -> _Source:
    return _Source(id_, "SDO", instrument, wavelength, label, sdo_code=code)


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
        url=f"{_SUVI_BASE}/195/latest.png",
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


def _response(src: _Source, ts: datetime, thumb: str, full: str) -> SolarImageResponse:
    return SolarImageResponse(
        id=src.id,
        source=src.source,
        instrument=src.instrument,
        wavelength=src.label,
        timestamp=ts,
        thumbnail_url=_with_cache_bust(thumb, ts),
        full_url=_with_cache_bust(full, ts),
    )


async def _build_all(sources: list[_Source]) -> list[SolarImageResponse]:
    """Responses in catalog order. An SDO channel no feed could supply is left out
    rather than shown as a stale frame stamped with the current time."""
    fixed = [s for s in sources if s.url]
    async with httpx.AsyncClient() as client:

        async def sdo_frames():
            return await latest_sdo_frames(client) if any(s.sdo_code for s in sources) else {}

        sdo, fixed_times = await asyncio.gather(
            sdo_frames(),
            asyncio.gather(*(_observation_time(client, s.url) for s in fixed)),
        )
    fixed_ts = {s.id: ts for s, ts in zip(fixed, fixed_times)}

    out: list[SolarImageResponse] = []
    for src in sources:
        if src.url:
            out.append(_response(src, fixed_ts[src.id], src.url, src.url))
        elif frame := sdo.get(src.sdo_code):
            out.append(_response(src, frame.time, frame.thumb_url, frame.full_url))
    return out


async def get_latest_solar_images() -> list[SolarImageResponse]:
    return await _build_all(CATALOG)


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
    return await _build_all(matches)
