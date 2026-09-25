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
import time
from dataclasses import dataclass
from datetime import date, datetime, timezone
from email.utils import parsedate_to_datetime

import httpx

from app.config import settings
from app.schemas.solar_image_schema import SolarArchiveImage, SolarArchiveResponse

_NOAA_FRM = "NOAA_SWPC_Observer"
_TARGET_PX = 1024
DEFAULT_TIME = "12:00"

# Near-real-time browse frames (same sources the Overview/Solar-Images pages use).
# Helioviewer's science archive lags real time by hours-to-days, so its "closest"
# frame is stale; in *latest* mode we display these instead so the archive looks
# current, while the raw downloads still resolve to the newest *science* product.
_SDO_BROWSE = "https://sdo.gsfc.nasa.gov/assets/img/latest/latest_2048_{code}.jpg"
_LASCO_BROWSE = "https://soho.nascom.nasa.gov/data/realtime/{cam}/1024/latest.jpg"
_BROWSE_URL = {
    "aia094": _SDO_BROWSE.format(code="0094"),
    "aia131": _SDO_BROWSE.format(code="0131"),
    "aia171": _SDO_BROWSE.format(code="0171"),
    "aia193": _SDO_BROWSE.format(code="0193"),
    "aia211": _SDO_BROWSE.format(code="0211"),
    "aia304": _SDO_BROWSE.format(code="0304"),
    "aia335": _SDO_BROWSE.format(code="0335"),
    "aia1600": _SDO_BROWSE.format(code="1600"),
    "hmic": _SDO_BROWSE.format(code="HMIIC"),
    "hmib": _SDO_BROWSE.format(code="HMIB"),
    "lascoc2": _LASCO_BROWSE.format(cam="c2"),
    "lascoc3": _LASCO_BROWSE.format(cam="c3"),
}

# SDO's *dated* browse archive holds timestamped full-disk frames per day (unlike
# Helioviewer, which lags), so browsing a past date+time returns a real frame from
# that day rather than the nearest ingested science frame (which may be days off).
# Files are ``YYYYMMDD_HHMMSS_<res>_<code>.jpg``. SOHO has no equivalent dated JPEG
# archive, so LASCO history falls back to Helioviewer. Codes match _BROWSE_URL.
_SDO_BROWSE_DIR = "https://sdo.gsfc.nasa.gov/assets/img/browse/{y:04d}/{m:02d}/{d:02d}/"
_SDO_BROWSE_RES = 2048
_BROWSE_CODE = {
    "aia094": "0094", "aia131": "0131", "aia171": "0171", "aia193": "0193",
    "aia211": "0211", "aia304": "0304", "aia335": "0335", "aia1600": "1600",
    "hmic": "HMIIC", "hmib": "HMIB",
}


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


# A dated browse/JSOC directory listing is ~1-2 MB and immutable once the day is
# past, so cache it in-process to avoid re-downloading it every time the user
# scrubs to another time on the same day.
_LISTING_TTL = 3600.0
_listing_cache: dict[str, tuple[float, str]] = {}


async def _cached_listing(client: httpx.AsyncClient, url: str) -> str:
    now = time.monotonic()
    hit = _listing_cache.get(url)
    if hit and hit[0] > now:
        return hit[1]
    text = await _listing(client, url)
    if len(_listing_cache) > 32:  # crude bound; these are large
        _listing_cache.clear()
    _listing_cache[url] = (now + _LISTING_TTL, text)
    return text


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


async def _browse_time(client: httpx.AsyncClient, url: str) -> datetime:
    """Frame time of a near-real-time browse image, from its Last-Modified header."""
    try:
        r = await client.head(url, timeout=10, follow_redirects=True)
        lm = r.headers.get("last-modified")
        if lm:
            return parsedate_to_datetime(lm).astimezone(timezone.utc)
    except Exception:
        pass
    return datetime.now(timezone.utc)


def _cache_busted(url: str, ts: datetime) -> str:
    return f"{url}?ts={int(ts.timestamp())}"


def _browse_dir_url(dt: datetime) -> str:
    return _SDO_BROWSE_DIR.format(y=dt.year, m=dt.month, d=dt.day)


def _resolve_browse_frame(
    listing: str, dir_url: str, code: str, target: datetime
) -> tuple[str, datetime] | None:
    """Nearest SDO dated-browse frame for ``code`` on the listed day (or None)."""
    rx = re.compile(rf"(\d{{8}})_(\d{{6}})_{_SDO_BROWSE_RES}_{re.escape(code)}\.jpg")
    best_name: str | None = None
    best_dt: datetime | None = None
    for m in rx.finditer(listing):
        dt = datetime.strptime(m.group(1) + m.group(2), "%Y%m%d%H%M%S").replace(
            tzinfo=timezone.utc
        )
        if best_dt is None or abs((dt - target).total_seconds()) < abs(
            (best_dt - target).total_seconds()
        ):
            best_name, best_dt = m.group(0), dt
    return (dir_url + best_name, best_dt) if best_name else None


def _frame_iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _reference_instant(d: date, time_hm: str, latest: bool) -> datetime:
    """The instant to resolve images against, never in the future.

    ``latest`` asks for the newest frame available on the selected day (its
    end-of-day), which for *today* resolves to the most recent image overall —
    that's how the archive surfaces current data. Otherwise it's the requested
    ``time_hm`` on ``d``. Either way it's clamped to "now" so we never ask
    Helioviewer for a future timestamp (which would resolve to a stale frame).
    """
    now = datetime.now(timezone.utc)
    if latest:
        ref = datetime(d.year, d.month, d.day, 23, 59, 59, tzinfo=timezone.utc)
    else:
        try:
            h, m = (int(x) for x in time_hm.split(":"))
        except ValueError:
            h, m = 12, 0
        ref = datetime(d.year, d.month, d.day, h, m, tzinfo=timezone.utc)
    return min(ref, now)


def _archive_image(
    src: _Source,
    display_time: datetime | None,
    image_url: str,
    dl_dt: datetime,
    with_events: bool,
) -> SolarArchiveImage:
    """One archive entry. Downloads target ``dl_dt`` — the frame actually shown —
    so "what you see is what you download" (subject to each product's archive)."""
    fd, fhm = dl_dt.date(), dl_dt.strftime("%H:%M")
    return SolarArchiveImage(
        id=src.id,
        source=src.source,
        instrument=src.instrument,
        measurement=src.measurement,
        label=src.label,
        source_id=src.source_id,
        supports_events=src.supports_events,
        time=display_time,
        image_url=image_url,
        png_download_url=_png_download_path(fd, fhm, src.id, with_events),
        jp2_download_url=_jp2_download_path(fd, fhm, src.id),
        fits_available=src.fits_provider is not None,
        fts_download_url=(
            _fts_download_path(fd, fhm, src.id) if src.fits_provider else None
        ),
    )


async def _historical_images(
    client: httpx.AsyncClient, ref: datetime, with_events: bool
) -> list[SolarArchiveImage]:
    """Archived frames for a past date+time.

    SDO/AIA + HMI come from the *dated* browse archive, so the requested time
    resolves to a real frame from that day. LASCO (no dated archive) — and any
    disk image when the NOAA active-region overlay is requested, since browse
    frames can't carry it — fall back to Helioviewer's nearest frame, labelled
    with its actual time.
    """
    dir_url = _browse_dir_url(ref)
    listing = ""
    if not with_events:
        try:
            listing = await _cached_listing(client, dir_url)
        except Exception:
            listing = ""  # listing unavailable -> Helioviewer fallback below

    # Resolve each source to a dated browse frame where possible; only the leftovers
    # (LASCO, or anything when the overlay is on) need a Helioviewer getClosestImage.
    browse_by_id = {
        src.id: _resolve_browse_frame(listing, dir_url, code, ref)
        for src in CATALOG
        if (code := _BROWSE_CODE.get(src.id)) and listing
    }
    hv_srcs = [s for s in CATALOG if not browse_by_id.get(s.id)]
    hv_times = await asyncio.gather(
        *[_closest_time(client, s, _frame_iso(ref)) for s in hv_srcs]
    )
    hv_by_id = {s.id: t for s, t in zip(hv_srcs, hv_times)}

    images: list[SolarArchiveImage] = []
    for src in CATALOG:
        browse = browse_by_id.get(src.id)
        if browse:
            url, frame_dt = browse
            images.append(
                _archive_image(src, frame_dt, _cache_busted(url, frame_dt), frame_dt, with_events)
            )
        else:
            hv_t = hv_by_id.get(src.id)
            frame = hv_t or ref
            images.append(
                _archive_image(
                    src, hv_t, screenshot_url(src, _frame_iso(frame), with_events), frame, with_events
                )
            )
    return images


async def get_archive_images(
    d: date, time_hm: str, with_events: bool, latest: bool = False
) -> SolarArchiveResponse:
    ref = _reference_instant(d, time_hm, latest)
    async with httpx.AsyncClient(timeout=30) as client:
        if latest:
            # Latest view: fresh near-real-time browse frame for the display, newest
            # available *science* frame (Helioviewer/JSOC lag real time) for downloads.
            sci_times = await asyncio.gather(
                *[_closest_time(client, s, _frame_iso(ref)) for s in CATALOG]
            )
            browse_times = await asyncio.gather(
                *[_browse_time(client, _BROWSE_URL[s.id]) for s in CATALOG]
            )
            images = [
                _archive_image(
                    src,
                    br_t,
                    _cache_busted(_BROWSE_URL[src.id], br_t or ref),
                    sci_t or ref,
                    with_events,
                )
                for src, sci_t, br_t in zip(CATALOG, sci_times, browse_times)
            ]
        else:
            images = await _historical_images(client, ref, with_events)

    return SolarArchiveResponse(
        date=d.isoformat(),
        time=ref.strftime("%H:%M"),
        with_events=with_events,
        latest=latest,
        images=images,
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
