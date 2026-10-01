"""Newest near-real-time SDO full-disk frames, from whichever feed is still live.

SDO publishes quick-look JPEGs in two places: a fixed-name ``latest/`` folder and a
dated per-frame archive (``browse/YYYY/MM/DD/YYYYMMDD_HHMMSS_<res>_<code>.jpg``).
On 2026-09-21 the ``latest/`` folder froze while the dated archive kept updating,
and on 2026-09-24 HMI frames stopped appearing in either — though JSOC's own HMI
quick-looks stayed current. No single feed can be trusted to stay live, so each
channel resolves to the newest frame among:

1. SDO's dated browse archive (newest-first listing, read only as far as needed),
2. JSOC's HMI quick-looks (continuum + magnetogram only),
3. SDO's ``latest/`` copy (HEAD Last-Modified) — only when 1 and 2 found nothing.

Used by the Overview / Solar Images gallery and the Archive's "latest" view.
"""
from __future__ import annotations

import asyncio
import logging
import re
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

import httpx

logger = logging.getLogger(__name__)

SDO_LATEST = "https://sdo.gsfc.nasa.gov/assets/img/latest"
SDO_BROWSE_DIR = "https://sdo.gsfc.nasa.gov/assets/img/browse/{d:%Y/%m/%d}/"
JSOC_HMI_LATEST = "https://jsoc1.stanford.edu/data/hmi/images/latest"

# Browse codes of every SDO channel the app shows.
SDO_CODES = ("0094", "0131", "0171", "0193", "0211", "0304", "0335", "1600", "HMIIC", "HMIB")

# JSOC equivalents: code -> (thumbnail, full size, key in its image_times_UTC file).
# colInt is the colourised continuum; Mag is the grey line-of-sight magnetogram.
_JSOC_HMI = {
    "HMIIC": ("HMI_latest_colInt_256x256.jpg", "HMI_latest_colInt_1024x1024.jpg", "colorIc"),
    "HMIB": ("HMI_latest_Mag_256x256.gif", "HMI_latest_Mag_1024x1024.gif", "magnetogram"),
}

# ``?C=N;O=D`` sorts the Apache listing by name descending, i.e. newest frame first.
# Each frame is listed at 512/1024/2048/4096 px, so matching one size gives one row
# per frame (and the code match is exact: HMIB never picks up HMIBC).
_ROW_RE = re.compile(r'href="(\d{8}_\d{6})_2048_([A-Z0-9]+)\.jpg"')

# Stop reading once rows are this much older than the newest frame in the archive:
# a channel with nothing in that window (e.g. HMI since 2026-09-24) isn't live there,
# and reading on would pull the whole ~1 MB day listing for nothing.
_SCAN_WINDOW = timedelta(hours=3)

# The gallery, Overview and Archive all poll every few minutes; SDO's cadence is
# ~10 min, so sharing one lookup briefly costs no freshness.
_CACHE_TTL = 90.0


@dataclass(frozen=True)
class Frame:
    time: datetime  # observation time (UTC)
    thumb_url: str  # 256-512 px
    full_url: str   # 1024-2048 px


_cache: tuple[float, dict[str, Frame]] | None = None


def _utc(stamp: str) -> datetime:
    return datetime.strptime(stamp, "%Y%m%d_%H%M%S").replace(tzinfo=timezone.utc)


async def _scan_browse_day(
    client: httpx.AsyncClient, day: date, codes: set[str], anchor: datetime | None
) -> tuple[dict[str, Frame], datetime | None, bool]:
    """Newest browse frame per code on ``day``, within the scan window of ``anchor``.

    Returns ``(frames, anchor, exhausted)``: ``anchor`` is the newest frame time
    seen so far (the window's reference) and ``exhausted`` says the listing was
    read to its end, so an older day could still hold frames inside the window.
    """
    dir_url = SDO_BROWSE_DIR.format(d=day)
    found: dict[str, Frame] = {}
    async with client.stream("GET", dir_url + "?C=N;O=D", timeout=20) as r:
        if r.status_code != 200:  # e.g. today's folder not created yet
            return found, anchor, True
        async for row in r.aiter_lines():
            m = _ROW_RE.search(row)
            if not m:
                continue
            stamp, code = m.groups()
            dt = _utc(stamp)
            anchor = anchor or dt
            if anchor - dt > _SCAN_WINDOW:
                return found, anchor, False
            if code in codes and code not in found:
                found[code] = Frame(
                    dt, f"{dir_url}{stamp}_512_{code}.jpg", f"{dir_url}{stamp}_2048_{code}.jpg"
                )
                if len(found) == len(codes):
                    return found, anchor, False
    return found, anchor, True


async def _browse_frames(client: httpx.AsyncClient) -> dict[str, Frame]:
    """Newest dated-browse frames, reaching back into yesterday's folder only when
    today's is short (just after 00:00 UTC) and the window extends past it."""
    today = datetime.now(timezone.utc).date()
    found: dict[str, Frame] = {}
    anchor: datetime | None = None
    for day in (today, today - timedelta(days=1)):
        missing = set(SDO_CODES) - found.keys()
        if not missing:
            break
        frames, anchor, exhausted = await _scan_browse_day(client, day, missing, anchor)
        found.update(frames)
        if not exhausted:
            break
    return found


async def _jsoc_hmi_frames(client: httpx.AsyncClient) -> dict[str, Frame]:
    """JSOC's HMI quick-looks, timed by its ``image_times_UTC`` manifest
    (lines like ``colorIc:\\t20261001_155923``)."""
    r = await client.get(f"{JSOC_HMI_LATEST}/image_times_UTC", timeout=10)
    r.raise_for_status()
    stamps = {
        key.strip(): value.strip()
        for key, _, value in (line.partition(":") for line in r.text.splitlines())
    }
    frames: dict[str, Frame] = {}
    for code, (thumb, full, key) in _JSOC_HMI.items():
        try:
            dt = _utc(stamps.get(key, ""))
        except ValueError:
            continue
        frames[code] = Frame(dt, f"{JSOC_HMI_LATEST}/{thumb}", f"{JSOC_HMI_LATEST}/{full}")
    return frames


async def _sdo_latest_frame(client: httpx.AsyncClient, code: str) -> Frame | None:
    """SDO's fixed-name ``latest/`` copy, timed by Last-Modified (last resort)."""
    thumb = f"{SDO_LATEST}/latest_512_{code}.jpg"
    try:
        r = await client.head(thumb, timeout=10, follow_redirects=True)
    except httpx.HTTPError:
        return None
    lm = r.headers.get("last-modified")
    if r.status_code != 200 or not lm:
        return None
    dt = parsedate_to_datetime(lm).astimezone(timezone.utc)
    return Frame(dt, thumb, f"{SDO_LATEST}/latest_2048_{code}.jpg")


async def latest_sdo_frames(client: httpx.AsyncClient) -> dict[str, Frame]:
    """Newest available frame per code in ``SDO_CODES`` (absent if none was found)."""
    global _cache
    now = time.monotonic()
    if _cache and _cache[0] > now:
        return _cache[1]

    candidates: dict[str, list[Frame]] = {code: [] for code in SDO_CODES}
    results = await asyncio.gather(
        _browse_frames(client), _jsoc_hmi_frames(client), return_exceptions=True
    )
    for name, result in zip(("SDO browse archive", "JSOC HMI"), results):
        if isinstance(result, BaseException):  # a failed feed just contributes nothing
            logger.warning("%s lookup failed: %r", name, result)
            continue
        for code, frame in result.items():
            candidates[code].append(frame)

    missing = [code for code, frames in candidates.items() if not frames]
    fallbacks = await asyncio.gather(*(_sdo_latest_frame(client, c) for c in missing))
    for code, frame in zip(missing, fallbacks):
        if frame:
            candidates[code].append(frame)

    frames = {code: max(fs, key=lambda f: f.time) for code, fs in candidates.items() if fs}
    _cache = (now + _CACHE_TTL, frames)
    return frames
