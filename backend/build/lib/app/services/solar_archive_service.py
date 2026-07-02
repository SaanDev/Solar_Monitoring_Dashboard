"""Historical solar images via the Helioviewer API.

Helioviewer renders a PNG for a given time + source (``takeScreenshot``) and stores
the science image as JPEG2000 (``getJP2Image`` — the "raw" product offered here).
Disk images (SDO/AIA, SDO/HMI) can be overlaid with HEK **NOAA SWPC active
regions** (``events=[AR,NOAA_SWPC_Observer,1]``).

Display images are served directly from Helioviewer (offloaded, CDN-cached);
downloads are proxied through our API so they arrive as attachments.
"""
from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from datetime import date, datetime, timezone

import httpx

from app.config import settings
from app.schemas.solar_image_schema import SolarArchiveImage, SolarArchiveResponse

_NOAA_FRM = "NOAA_SWPC_Observer"
_TARGET_PX = 1024
DEFAULT_TIME = "12:00"


@dataclass(frozen=True)
class _Source:
    id: str
    source: str
    instrument: str
    measurement: str
    label: str
    source_id: int       # Helioviewer sourceId
    fov_arcsec: int      # half-width of the rendered region
    supports_events: bool
    # Raw FITS via JSOC synoptic archives: provider "aia" (wave code) or "hmi"
    # (series). None = no direct FITS source (e.g. LASCO).
    fits_provider: str | None = None
    fits_key: str | None = None


# Full-disk EUV/visible (SDO) + coronagraph (SOHO/LASCO). Order = display order.
CATALOG: list[_Source] = [
    _Source("aia094", "SDO", "AIA", "94", "AIA 94 Å", 8, 1250, True, "aia", "0094"),
    _Source("aia131", "SDO", "AIA", "131", "AIA 131 Å", 9, 1250, True, "aia", "0131"),
    _Source("aia171", "SDO", "AIA", "171", "AIA 171 Å", 10, 1250, True, "aia", "0171"),
    _Source("aia193", "SDO", "AIA", "193", "AIA 193 Å", 11, 1250, True, "aia", "0193"),
    _Source("aia211", "SDO", "AIA", "211", "AIA 211 Å", 12, 1250, True, "aia", "0211"),
    _Source("aia304", "SDO", "AIA", "304", "AIA 304 Å", 13, 1250, True, "aia", "0304"),
    _Source("aia335", "SDO", "AIA", "335", "AIA 335 Å", 14, 1250, True, "aia", "0335"),
    _Source("aia1600", "SDO", "AIA", "1600", "AIA 1600 Å", 15, 1250, True, "aia", "1600"),
    # The JSOC synoptic FITS archive carries HMI magnetograms (M_720s) but not
    # continuum, so only the magnetogram offers a raw FITS download.
    _Source("hmic", "SDO", "HMI", "continuum", "HMI Continuum", 18, 1250, True),
    _Source("hmib", "SDO", "HMI", "magnetogram", "HMI Magnetogram", 19, 1250, True, "hmi", "M_720s"),
    _Source("lascoc2", "SOHO", "LASCO", "C2", "LASCO C2", 4, 6000, False),
    _Source("lascoc3", "SOHO", "LASCO", "C3", "LASCO C3", 5, 30000, False),
]
_BY_ID = {s.id: s for s in CATALOG}


def _iso(d: date, time_hm: str) -> str:
    return f"{d.isoformat()}T{time_hm}:00Z"


def _image_scale(fov_arcsec: int) -> float:
    return round((2 * fov_arcsec) / _TARGET_PX, 4)


def screenshot_url(src: _Source, date_iso: str, with_events: bool) -> str:
    """Direct Helioviewer takeScreenshot URL (brackets percent-encoded)."""
    fov = src.fov_arcsec
    parts = [
        f"imageScale={_image_scale(fov)}",
        f"layers=%5B{src.source_id},1,100%5D",
        f"date={date_iso}",
        f"x1={-fov}", f"y1={-fov}", f"x2={fov}", f"y2={fov}",
        "display=true",
        "watermark=false",
    ]
    if with_events and src.supports_events:
        parts.append(f"events=%5BAR,{_NOAA_FRM},1%5D")
        parts.append("eventLabels=true")
    else:
        parts.append("events=")
        parts.append("eventLabels=false")
    return f"{settings.helioviewer_base_url}/v2/takeScreenshot/?" + "&".join(parts)


def _png_download_path(d: date, time_hm: str, key: str, with_events: bool) -> str:
    flag = "true" if with_events else "false"
    return (
        f"/api/solar/archive/image?date={d.isoformat()}&time={time_hm}"
        f"&id={key}&events={flag}&download=1"
    )


def _jp2_download_path(d: date, time_hm: str, key: str) -> str:
    return f"/api/solar/archive/jp2?date={d.isoformat()}&time={time_hm}&id={key}&download=1"


def _fts_download_path(d: date, time_hm: str, key: str) -> str:
    return f"/api/solar/archive/fits?date={d.isoformat()}&time={time_hm}&id={key}&download=1"


# Raw FITS resolution against the JSOC synoptic archives. Both providers expose a
# browsable directory per day/hour; we pick the file closest to the requested time.
_AIA_RE = re.compile(r"AIA(\d{8})_(\d{4})_(\d{4})\.fits")
_HMI_RE = re.compile(r"hmi\.(M_720s|Ic_720s)\.(\d{8})_(\d{6})_TAI\.fits")


async def _listing(client: httpx.AsyncClient, url: str) -> str:
    r = await client.get(url, timeout=40)
    r.raise_for_status()
    return r.text


def _nearest(candidates: list[tuple[datetime, str]], target: datetime) -> str | None:
    if not candidates:
        return None
    return min(candidates, key=lambda c: abs((c[0] - target).total_seconds()))[1]


async def _resolve_fits(
    client: httpx.AsyncClient, src: _Source, dt: datetime
) -> tuple[str, str] | None:
    """Return (url, filename) of the archive FITS nearest ``dt`` for this source."""
    if src.fits_provider == "aia":
        dir_url = (
            f"{settings.jsoc_base_url}/data/aia/synoptic/"
            f"{dt:%Y/%m/%d}/H{dt:%H}00/"
        )
        text = await _listing(client, dir_url)
        cands = [
            (datetime.strptime(ymd + hm, "%Y%m%d%H%M").replace(tzinfo=timezone.utc), m.group(0))
            for m in _AIA_RE.finditer(text)
            for ymd, hm, wave in [(m.group(1), m.group(2), m.group(3))]
            if wave == src.fits_key
        ]
    elif src.fits_provider == "hmi":
        dir_url = f"{settings.jsoc_base_url}/data/hmi/fits/{dt:%Y/%m/%d}/"
        text = await _listing(client, dir_url)
        cands = [
            (datetime.strptime(ymd + hms, "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc), m.group(0))
            for m in _HMI_RE.finditer(text)
            for series, ymd, hms in [(m.group(1), m.group(2), m.group(3))]
            if series == src.fits_key
        ]
    else:
        return None

    fname = _nearest(cands, dt)
    return (dir_url + fname, fname) if fname else None


async def _closest_time(client: httpx.AsyncClient, src: _Source, date_iso: str) -> datetime | None:
    try:
        r = await client.get(
            f"{settings.helioviewer_base_url}/v2/getClosestImage/",
            params={"date": date_iso, "sourceId": src.source_id},
            timeout=20,
        )
        r.raise_for_status()
        raw = r.json()["date"]  # "YYYY-MM-DD HH:MM:SS"
        return datetime.strptime(raw, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
    except Exception:
        return None


async def get_archive_images(d: date, time_hm: str, with_events: bool) -> SolarArchiveResponse:
    date_iso = _iso(d, time_hm)
    async with httpx.AsyncClient(timeout=30) as client:
        times = await asyncio.gather(*[_closest_time(client, s, date_iso) for s in CATALOG])

    images = [
        SolarArchiveImage(
            id=src.id,
            source=src.source,
            instrument=src.instrument,
            measurement=src.measurement,
            label=src.label,
            source_id=src.source_id,
            supports_events=src.supports_events,
            time=t,
            image_url=screenshot_url(src, date_iso, with_events),
            png_download_url=_png_download_path(d, time_hm, src.id, with_events),
            jp2_download_url=_jp2_download_path(d, time_hm, src.id),
            fits_available=src.fits_provider is not None,
            fts_download_url=(
                _fts_download_path(d, time_hm, src.id) if src.fits_provider else None
            ),
        )
        for src, t in zip(CATALOG, times)
    ]
    return SolarArchiveResponse(
        date=d.isoformat(), time=time_hm, with_events=with_events, images=images
    )


async def fetch_screenshot_png(
    d: date, time_hm: str, key: str, with_events: bool
) -> bytes | None:
    src = _BY_ID.get(key)
    if src is None:
        return None
    url = screenshot_url(src, _iso(d, time_hm), with_events)
    async with httpx.AsyncClient(timeout=90, follow_redirects=True) as client:
        r = await client.get(url)
        r.raise_for_status()
        return r.content


async def fetch_jp2(d: date, time_hm: str, key: str) -> tuple[bytes, str] | None:
    src = _BY_ID.get(key)
    if src is None:
        return None
    async with httpx.AsyncClient(timeout=90, follow_redirects=True) as client:
        r = await client.get(
            f"{settings.helioviewer_base_url}/v2/getJP2Image/",
            params={"date": _iso(d, time_hm), "sourceId": src.source_id},
        )
        r.raise_for_status()
        fname = f"{src.id}_{d.isoformat()}_{time_hm.replace(':', '')}.jp2"
        return r.content, fname


async def fetch_fts(d: date, time_hm: str, key: str) -> tuple[bytes, str] | None:
    """Raw FITS bytes nearest the requested time (AIA/HMI synoptic archives)."""
    src = _BY_ID.get(key)
    if src is None or src.fits_provider is None:
        return None
    h, m = (int(x) for x in time_hm.split(":"))
    dt = datetime(d.year, d.month, d.day, h, m, tzinfo=timezone.utc)
    async with httpx.AsyncClient(timeout=120, follow_redirects=True) as client:
        resolved = await _resolve_fits(client, src, dt)
        if resolved is None:
            return None
        url, fname = resolved
        r = await client.get(url)
        r.raise_for_status()
        return r.content, fname
