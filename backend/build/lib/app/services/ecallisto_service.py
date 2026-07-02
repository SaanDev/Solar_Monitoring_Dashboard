"""e-CALLISTO service.

Two flows, both prioritising the Sri Lanka station (SRI-Lanka):
  1. Live  : latest SRI-Lanka dynamic spectrum from the archive.
  2. Bursts: events from the latest burst-list date; for each, the relevant
             FITS (SRI-Lanka when it observed the burst, else a participating
             station) is located in the archive and rendered on demand.
"""
from dataclasses import dataclass
from datetime import date, datetime, timezone, timedelta
from pathlib import Path

from app.processing.dynamic_spectrum import process_fits
from app.collectors.collect_ecallisto import (
    FitsFile,
    list_day_files,
    files_for_station,
    files_for_station_focus,
    focuses_for_station,
    latest_file_for_station,
    file_covering,
    stations_on,
    download_fits,
    fetch_fits_bytes,
)
from app.collectors.collect_burst_list import (
    BurstEvent,
    fetch_burst_list_text,
    parse_burst_list,
    get_latest_burst_events as fetch_latest_burst_events,
)
from app.schemas.radio_schema import (
    RadioStationResponse,
    RadioSpectrumResponse,
    RadioLiveStation,
    RadioLiveStationsResponse,
    RadioArchiveStation,
    RadioArchiveStationsResponse,
    RadioArchiveFile,
    RadioArchiveFilesResponse,
    BurstEventSummary,
    BurstEventsResponse,
    BurstSpectrumResponse,
)

SRI_LANKA = "SRI-Lanka"

_STATIONS: list[RadioStationResponse] = [
    RadioStationResponse(id="SRI-Lanka", name="Sri Lanka (ACCIMT)", location="Sri Lanka", freq_min_mhz=45.0, freq_max_mhz=84.5, active=True),
    RadioStationResponse(id="INDIA-UDAIPUR", name="India Udaipur", location="India", freq_min_mhz=45.0, freq_max_mhz=870.0, active=True),
    RadioStationResponse(id="INDIA-OOTY", name="India Ooty", location="India", freq_min_mhz=45.0, freq_max_mhz=870.0, active=True),
    RadioStationResponse(id="Australia-ASSA", name="Australia ASSA", location="Australia", freq_min_mhz=45.0, freq_max_mhz=870.0, active=True),
    RadioStationResponse(id="ALASKA-COHOE", name="Alaska Cohoe", location="USA", freq_min_mhz=45.0, freq_max_mhz=870.0, active=True),
    RadioStationResponse(id="GLASGOW", name="Glasgow", location="UK", freq_min_mhz=45.0, freq_max_mhz=870.0, active=True),
    RadioStationResponse(id="HUMAIN", name="Humain", location="Belgium", freq_min_mhz=45.0, freq_max_mhz=870.0, active=True),
]

# Station ids we have catalog metadata for (the archive lists many more stations).
_KNOWN_STATION_IDS = {s.id for s in _STATIONS}

# Cached burst-event resolution (so /latest and /spectrum agree on indexing).
_resolved_events: list["_ResolvedBurst"] = []
_resolved_date: date | None = None
# Same, keyed by explicit date for the archive (so list/spectrum agree per date).
_resolved_by_date: dict[date, list["_ResolvedBurst"]] = {}

# Processed-spectrum metadata cache, keyed by output PNG name (avoids re-downloading
# a FITS file just to re-read its header once the PNG is already rendered).
_meta_cache: dict[str, dict] = {}


@dataclass
class _ResolvedBurst:
    event: BurstEvent
    # Ordered (station, file) candidates, Sri Lanka first, for fallback on failure.
    candidates: list[tuple[str, FitsFile]]

    @property
    def station_used(self) -> str | None:
        return self.candidates[0][0] if self.candidates else None

    @property
    def has_fits(self) -> bool:
        return bool(self.candidates)


def list_stations() -> list[RadioStationResponse]:
    return _STATIONS


# Bump when the rendering changes so stale cached PNGs are regenerated.
# v4: x-axis ticks switched from seconds-from-start to wall-clock UTC.
_RENDER_VERSION = "v4"


def _cache_name(fits_filename: str) -> str:
    base = fits_filename.replace(".fit.gz", "").replace(".fit", "")
    return f"{base}_{_RENDER_VERSION}.png"


def _spectrum_url(image_filename: str) -> str:
    return f"/api/radio/spectra/{image_filename}"


def _spectrum_response(
    station: str, meta: dict, fits_filename: str | None = None
) -> RadioSpectrumResponse:
    return RadioSpectrumResponse(
        station=station,
        start_time=meta["start_time"],
        end_time=meta["end_time"],
        freq_min_mhz=meta["freq_min_mhz"],
        freq_max_mhz=meta["freq_max_mhz"],
        image_url=_spectrum_url(meta["image_filename"]),
        processing_method=meta["processing_method"],
        fits_filename=fits_filename,
    )


def process_fits_file(fits_path: Path, station: str) -> RadioSpectrumResponse:
    meta = process_fits(fits_path, station=station)
    return RadioSpectrumResponse(
        station=meta["station"],
        start_time=meta["start_time"],
        end_time=meta["end_time"],
        freq_min_mhz=meta["freq_min_mhz"],
        freq_max_mhz=meta["freq_max_mhz"],
        image_url=_spectrum_url(meta["image_filename"]),
        processing_method=meta["processing_method"],
    )


async def _render_archive_file(f: FitsFile) -> dict:
    """Download and render an archive FITS file. Cached by output PNG name so a
    repeat request neither re-downloads nor re-renders."""
    out_name = _cache_name(f.filename)
    if out_name in _meta_cache:
        return _meta_cache[out_name]
    local = await download_fits(f.url)
    try:
        meta = process_fits(local, station=f.station, out_filename=out_name)
    finally:
        local.unlink(missing_ok=True)
    _meta_cache[out_name] = meta
    return meta


# ─── Live dynamic spectrum (any station / focus) ─────────────────────────────

# How many days back to search when recent days have no data.
_LIVE_LOOKBACK_DAYS = 21


async def _latest_day_with_data() -> tuple[date, list[FitsFile]] | None:
    """Most recent day (within the lookback window) that has any archive files."""
    now = datetime.now(timezone.utc)
    for back in range(_LIVE_LOOKBACK_DAYS + 1):
        day = (now - timedelta(days=back)).date()
        try:
            files = await list_day_files(day)
        except Exception:
            continue
        if files:
            return day, files
    return None


async def get_live_stations() -> RadioLiveStationsResponse:
    """Stations (with their focus codes) available on the most recent day with
    data — drives the homepage station/focus selectors."""
    result = await _latest_day_with_data()
    if result is None:
        return RadioLiveStationsResponse()
    day, files = result
    stations = [
        RadioLiveStation(
            id=sid,
            has_metadata=sid in _KNOWN_STATION_IDS,
            focuses=focuses_for_station(files, sid),
        )
        for sid in sorted(stations_on(files))
    ]
    return RadioLiveStationsResponse(date=day.isoformat(), stations=stations)


async def get_live_spectrum(
    station: str, focus: str | None = None
) -> RadioSpectrumResponse | None:
    """Latest available dynamic spectrum for ``station`` (optionally a specific
    ``focus`` code). Walks backwards day-by-day so the panel always shows the
    most recent spectrum even if the station has been offline for a while."""
    now = datetime.now(timezone.utc)
    for back in range(_LIVE_LOOKBACK_DAYS + 1):
        day = (now - timedelta(days=back)).date()
        try:
            files = await list_day_files(day)
        except Exception:
            continue
        if focus:
            sf = files_for_station_focus(files, station, focus)
            latest = sf[-1] if sf else None
        else:
            latest = latest_file_for_station(files, station)
        if not latest:
            continue
        meta = await _render_archive_file(latest)
        return _spectrum_response(station, meta, fits_filename=latest.filename)
    return None


async def get_sri_lanka_live() -> RadioSpectrumResponse | None:
    """Backwards-compatible helper: latest SRI-Lanka spectrum."""
    return await get_live_spectrum(SRI_LANKA)


# ─── Burst events ──────────────────────────────────────────────────────────────

def _candidates_for(event: BurstEvent, files: list[FitsFile]) -> list[tuple[str, FitsFile]]:
    """Ordered (station, file) candidates: Sri Lanka first, then other
    participating stations that have a covering file in the archive."""
    ordered = ([SRI_LANKA] if SRI_LANKA in event.stations else []) + [
        s for s in event.stations if s != SRI_LANKA
    ]
    out: list[tuple[str, FitsFile]] = []
    for station in ordered:
        f = file_covering(files, station, event.start_dt)
        if f is not None:
            out.append((station, f))
    return out


async def _resolve_events(d: date, events: list[BurstEvent]) -> list[_ResolvedBurst]:
    """Pair each burst with the archive FITS candidates that can render it, and
    cache the result by date so the list and the per-burst spectrum stay aligned."""
    try:
        files = await list_day_files(d)
    except Exception:
        files = []
    resolved = [_ResolvedBurst(event=ev, candidates=_candidates_for(ev, files)) for ev in events]
    _resolved_by_date[d] = resolved
    return resolved


def _summarize(d: date, resolved: list[_ResolvedBurst]) -> BurstEventsResponse:
    summaries = [
        BurstEventSummary(
            index=i,
            date=d.isoformat(),
            start=rb.event.start.strftime("%H:%M"),
            end=rb.event.end.strftime("%H:%M"),
            burst_type=rb.event.type,
            stations=rb.event.stations,
            station_used=rb.station_used,
            has_fits=rb.has_fits,
        )
        for i, rb in enumerate(resolved)
    ]
    sri_count = sum(1 for rb in resolved if SRI_LANKA in rb.event.stations)
    return BurstEventsResponse(
        date=d.isoformat(), count=len(summaries), sri_lanka_count=sri_count, events=summaries
    )


async def _spectrum_from(resolved: list[_ResolvedBurst], index: int) -> BurstSpectrumResponse | None:
    if index < 0 or index >= len(resolved):
        return None
    rb = resolved[index]
    if not rb.candidates:
        return None
    ev = rb.event
    # Try Sri Lanka first, falling back to other stations if a file is unreadable.
    for station, fits in rb.candidates:
        try:
            meta = await _render_archive_file(fits)
        except Exception:
            continue
        return BurstSpectrumResponse(
            index=index,
            date=ev.date.isoformat(),
            start=ev.start.strftime("%H:%M"),
            end=ev.end.strftime("%H:%M"),
            burst_type=ev.type,
            station_used=station,
            stations=ev.stations,
            start_time=meta["start_time"],
            end_time=meta["end_time"],
            freq_min_mhz=meta["freq_min_mhz"],
            freq_max_mhz=meta["freq_max_mhz"],
            image_url=_spectrum_url(meta["image_filename"]),
            processing_method=meta["processing_method"],
            fits_filename=fits.filename,
        )
    return None


# Latest burst list (used by the live solar-radio page).
async def get_latest_burst_events() -> BurstEventsResponse:
    global _resolved_events, _resolved_date

    latest_date, events = await fetch_latest_burst_events()
    if latest_date is None:
        _resolved_events, _resolved_date = [], None
        return BurstEventsResponse()

    resolved = await _resolve_events(latest_date, events)
    _resolved_events, _resolved_date = resolved, latest_date
    return _summarize(latest_date, resolved)


async def get_burst_spectrum(index: int) -> BurstSpectrumResponse | None:
    # Resolve the event list if the cache is empty (e.g. first call after restart).
    if not _resolved_events:
        await get_latest_burst_events()
    return await _spectrum_from(_resolved_events, index)


# ─── Archive: explicit date + station ───────────────────────────────────────


async def list_archive_stations(d: date) -> RadioArchiveStationsResponse:
    """Stations that have data in the archive on a given UTC date."""
    try:
        files = await list_day_files(d)
    except Exception:
        files = []
    stations = [
        RadioArchiveStation(id=sid, has_metadata=sid in _KNOWN_STATION_IDS)
        for sid in sorted(stations_on(files))
    ]
    return RadioArchiveStationsResponse(date=d.isoformat(), stations=stations)


async def list_archive_files(d: date, station: str) -> RadioArchiveFilesResponse:
    """The ~15-minute FITS segments available for a station on a given date."""
    try:
        files = await list_day_files(d)
    except Exception:
        files = []
    sf = files_for_station(files, station)
    return RadioArchiveFilesResponse(
        date=d.isoformat(),
        station=station,
        files=[RadioArchiveFile(filename=f.filename, start_time=f.start) for f in sf],
    )


async def get_archive_spectrum(
    d: date, station: str, filename: str | None
) -> RadioSpectrumResponse | None:
    """Render a dynamic spectrum for a station on a date. Without ``filename`` the
    latest segment of the day is used."""
    try:
        files = await list_day_files(d)
    except Exception:
        return None
    sf = files_for_station(files, station)
    if not sf:
        return None
    target = next((f for f in sf if f.filename == filename), None) if filename else sf[-1]
    if target is None:
        return None
    meta = await _render_archive_file(target)
    return _spectrum_response(station, meta, fits_filename=target.filename)


async def get_archive_spectrum_at(
    d: date, station: str, hhmm: str
) -> RadioSpectrumResponse | None:
    """Render the ~15-min segment for ``station`` covering ``hhmm`` (HH:MM UTC).

    Used to preview an official burst-list event, which gives a time + station
    rather than a specific file: the covering segment is located with
    ``file_covering`` (falling back to the nearest segment) and rendered."""
    try:
        files = await list_day_files(d)
    except Exception:
        return None
    try:
        target = datetime.combine(
            d, datetime.strptime(hhmm, "%H:%M").time(), tzinfo=timezone.utc
        )
    except ValueError:
        return None
    target_file = file_covering(files, station, target)
    if target_file is None:
        return None
    meta = await _render_archive_file(target_file)
    return _spectrum_response(station, meta, fits_filename=target_file.filename)


async def get_archive_fits(d: date, station: str, filename: str) -> tuple[bytes, str] | None:
    """Raw .fit.gz bytes for a specific archive file, for client download."""
    try:
        files = await list_day_files(d)
    except Exception:
        return None
    target = next(
        (f for f in files_for_station(files, station) if f.filename == filename), None
    )
    if target is None:
        return None
    content = await fetch_fits_bytes(target.url)
    return content, target.filename


async def get_burst_events_for_date(d: date) -> BurstEventsResponse:
    """Burst list for a specific UTC date (archive view)."""
    try:
        text = await fetch_burst_list_text(d.year, d.month)
    except Exception:
        return BurstEventsResponse(date=d.isoformat())
    events = sorted((e for e in parse_burst_list(text) if e.date == d), key=lambda e: e.start)
    resolved = await _resolve_events(d, events)
    return _summarize(d, resolved)


async def get_burst_spectrum_for_date(d: date, index: int) -> BurstSpectrumResponse | None:
    resolved = _resolved_by_date.get(d)
    if resolved is None:
        await get_burst_events_for_date(d)
        resolved = _resolved_by_date.get(d, [])
    return await _spectrum_from(resolved, index)
