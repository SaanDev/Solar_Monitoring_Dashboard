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
    latest_file_for_station,
    file_covering,
    download_fits,
)
from app.collectors.collect_burst_list import (
    BurstEvent,
    get_latest_burst_events as fetch_latest_burst_events,
)
from app.schemas.radio_schema import (
    RadioStationResponse,
    RadioSpectrumResponse,
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

# Cached burst-event resolution (so /latest and /spectrum agree on indexing).
_resolved_events: list["_ResolvedBurst"] = []
_resolved_date: date | None = None

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
_RENDER_VERSION = "v3"


def _cache_name(fits_filename: str) -> str:
    base = fits_filename.replace(".fit.gz", "").replace(".fit", "")
    return f"{base}_{_RENDER_VERSION}.png"


def _spectrum_url(image_filename: str) -> str:
    return f"/api/radio/spectra/{image_filename}"


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


# ─── Live Sri Lanka ────────────────────────────────────────────────────────────

# How many days back to search when recent days have no Sri Lanka data.
_LIVE_LOOKBACK_DAYS = 21


async def get_sri_lanka_live() -> RadioSpectrumResponse | None:
    """Latest available SRI-Lanka dynamic spectrum.

    Tries today and walks backwards until a day with SRI-Lanka data is found,
    so the panel always shows the most recent spectrum even if the station has
    been offline for a while.
    """
    now = datetime.now(timezone.utc)
    for back in range(_LIVE_LOOKBACK_DAYS + 1):
        day = (now - timedelta(days=back)).date()
        try:
            files = await list_day_files(day)
        except Exception:
            continue
        latest = latest_file_for_station(files, SRI_LANKA)
        if not latest:
            continue
        meta = await _render_archive_file(latest)
        return RadioSpectrumResponse(
            station=SRI_LANKA,
            start_time=meta["start_time"],
            end_time=meta["end_time"],
            freq_min_mhz=meta["freq_min_mhz"],
            freq_max_mhz=meta["freq_max_mhz"],
            image_url=_spectrum_url(meta["image_filename"]),
            processing_method=meta["processing_method"],
        )
    return None


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


async def get_latest_burst_events() -> BurstEventsResponse:
    global _resolved_events, _resolved_date

    latest_date, events = await fetch_latest_burst_events()
    if latest_date is None:
        _resolved_events, _resolved_date = [], None
        return BurstEventsResponse()

    try:
        files = await list_day_files(latest_date)
    except Exception:
        files = []

    resolved: list[_ResolvedBurst] = []
    summaries: list[BurstEventSummary] = []
    for i, ev in enumerate(events):
        rb = _ResolvedBurst(event=ev, candidates=_candidates_for(ev, files))
        resolved.append(rb)
        summaries.append(
            BurstEventSummary(
                index=i,
                date=latest_date.isoformat(),
                start=ev.start.strftime("%H:%M"),
                end=ev.end.strftime("%H:%M"),
                burst_type=ev.type,
                stations=ev.stations,
                station_used=rb.station_used,
                has_fits=rb.has_fits,
            )
        )

    _resolved_events, _resolved_date = resolved, latest_date
    sri_count = sum(1 for r in resolved if SRI_LANKA in r.event.stations)
    return BurstEventsResponse(
        date=latest_date.isoformat(),
        count=len(summaries),
        sri_lanka_count=sri_count,
        events=summaries,
    )


async def get_burst_spectrum(index: int) -> BurstSpectrumResponse | None:
    # Resolve the event list if the cache is empty (e.g. first call after restart).
    if not _resolved_events:
        await get_latest_burst_events()
    if index < 0 or index >= len(_resolved_events):
        return None

    rb = _resolved_events[index]
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
        )
    return None
