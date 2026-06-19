"""Access the e-CALLISTO FITS archive.

Source: https://soleil.i4ds.ch/solarradio/data/2002-20yy_Callisto/{YYYY}/{MM}/{DD}/
Files named {STATION}_{YYYYMMDD}_{HHMMSS}_{focus}.fit.gz, each ~15 minutes.
"""
from dataclasses import dataclass
from datetime import date, datetime, timezone, timedelta
from pathlib import Path
import re
import time as _time
import tempfile

import httpx

_ARCHIVE = "https://soleil.i4ds.ch/solarradio/data/2002-20yy_Callisto"
# Capture: full filename, station, YYYYMMDD, HHMMSS, focus code (trailing _NN).
_FILE_RE = re.compile(r'href="(([A-Za-z0-9\-]+)_(\d{8})_(\d{6})_(\d+)\.fit\.gz)"')
_FILE_DURATION = timedelta(minutes=15)

# Per-day directory listing cache: date -> (fetched_epoch, list[FitsFile])
_listing_cache: dict[date, tuple[float, list]] = {}
_CACHE_TTL_S = 600  # re-fetch today's listing every 10 min


@dataclass(frozen=True)
class FitsFile:
    station: str
    start: datetime
    filename: str
    url: str
    focus: str = ""  # trailing _NN focus/instrument code from the filename


def _day_url(d: date) -> str:
    return f"{_ARCHIVE}/{d.year}/{d.month:02d}/{d.day:02d}/"


async def list_day_files(d: date) -> list[FitsFile]:
    cached = _listing_cache.get(d)
    if cached and (_time.time() - cached[0]) < _CACHE_TTL_S:
        return cached[1]

    base = _day_url(d)
    async with httpx.AsyncClient(timeout=45) as client:
        r = await client.get(base)
        r.raise_for_status()
        text = r.text

    files: list[FitsFile] = []
    for fname, station, ymd, hms, focus in _FILE_RE.findall(text):
        try:
            start = datetime.strptime(ymd + hms, "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)
        except ValueError:
            continue
        files.append(
            FitsFile(station=station, start=start, filename=fname, url=base + fname, focus=focus)
        )

    _listing_cache[d] = (_time.time(), files)
    return files


def stations_on(files: list[FitsFile]) -> set[str]:
    return {f.station for f in files}


def files_for_station(files: list[FitsFile], station: str) -> list[FitsFile]:
    return sorted((f for f in files if f.station == station), key=lambda f: f.start)


def focuses_for_station(files: list[FitsFile], station: str) -> list[str]:
    """Distinct focus codes a station observed with on this day, ascending."""
    return sorted({f.focus for f in files if f.station == station}, key=lambda c: (len(c), c))


def files_for_station_focus(
    files: list[FitsFile], station: str, focus: str
) -> list[FitsFile]:
    return sorted(
        (f for f in files if f.station == station and f.focus == focus),
        key=lambda f: f.start,
    )


def latest_file_for_station(files: list[FitsFile], station: str) -> FitsFile | None:
    sf = files_for_station(files, station)
    return sf[-1] if sf else None


def file_covering(files: list[FitsFile], station: str, target: datetime) -> FitsFile | None:
    """File whose ~15-min window contains target, else the nearest earlier one."""
    sf = files_for_station(files, station)
    if not sf:
        return None
    covering = [f for f in sf if f.start <= target < f.start + _FILE_DURATION]
    if covering:
        return covering[-1]
    earlier = [f for f in sf if f.start <= target]
    if earlier:
        return earlier[-1]
    return min(sf, key=lambda f: abs((f.start - target).total_seconds()))


async def fetch_fits_bytes(url: str) -> bytes:
    """Raw .fit.gz content from the archive (used for client downloads)."""
    async with httpx.AsyncClient(timeout=60, follow_redirects=True) as client:
        r = await client.get(url)
        r.raise_for_status()
        return r.content


async def download_fits(url: str) -> Path:
    content = await fetch_fits_bytes(url)
    tmp = tempfile.NamedTemporaryFile(suffix=".fit.gz", delete=False)
    tmp.write(content)
    tmp.close()
    return Path(tmp.name)
