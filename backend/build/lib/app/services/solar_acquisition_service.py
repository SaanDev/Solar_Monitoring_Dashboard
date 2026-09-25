"""Multi-mission data acquisition for the Data Analysis feature.

Wraps the ported ``app.services.solar`` acquisition layer (instrument registry +
SunPy Fido search + JSOC ``drms`` fast path) and exposes the small set of
functions the ``/api/analysis`` router needs:

* :func:`observable_options` — the registry tree for the frontend's picker.
* :func:`run_search` / :func:`run_find_latest` — Fido search; the raw
  ``SunPySearchResult`` is cached server-side under a ``search_id`` so the follow
  up download can fetch exactly the rows the user selected.
* :func:`fetch_selected_job` — a background job (see ``job_manager``) that
  downloads the selected rows (JSOC fast path with server-side cutout/binning, or
  the VSO/Fido path) and builds a session via ``aia_data_service.build_session``.

SunPy/drms are imported lazily inside the ported modules, so importing this
service never requires the ``[sci]`` extra — only calling search/fetch does.
"""
from __future__ import annotations

import logging
import shutil
import threading
from collections import OrderedDict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4

from app.config import settings
from app.schemas.data_analysis_schema import (
    Observable,
    SearchRequest,
    SearchResponse,
    SearchRow,
)
from app.services import aia_data_service as data
from app.services.solar import instrument_profiles as profiles
from app.services.solar import jsoc_client as jsoc
from app.services.solar import sunpy_archive as archive
from app.services.solar.sunpy_archive import SunPyQuerySpec, SunPySearchResult

logger = logging.getLogger(__name__)

# ── observable registry → UI options ────────────────────────────────────────────


# Disk-EUV imagers classify_observable() doesn't enumerate (it targets the
# desktop tool's core set); classify_frame() handles these at session-build time,
# so mirror that here for the picker's tool gating.
_EXTRA_DISK_EUV = {"SWAP", "EIT", "EUI"}


def _science_class(entry: Any) -> str:
    """Science class for a registry entry (drives which tools apply)."""
    if str(entry.instrument or "").upper() == "SECCHI":
        value: Any = (entry.spacecraft, entry.detector, entry.default_wavelength)
    else:
        value = entry.detector or entry.default_product or entry.default_wavelength
    cls = profiles.classify_observable(entry.instrument, value)
    if cls == profiles.UNKNOWN and str(entry.instrument or "").upper() in _EXTRA_DISK_EUV:
        return profiles.DISK_EUV
    return cls


def observable_options() -> list[Observable]:
    """The multi-mission observable tree (map imagers only — the image workbench
    can't render GOES/XRS timeseries)."""
    out: list[Observable] = []
    for e in archive.INSTRUMENT_REGISTRY:
        if e.data_kind != archive.DATA_KIND_MAP:
            continue
        out.append(
            Observable(
                key=e.key,
                label=e.label,
                spacecraft=e.spacecraft,
                instrument=e.instrument,
                detector=e.detector,
                data_kind=e.data_kind,
                science_class=_science_class(e),
                supports_wavelength=e.supports_wavelength,
                supports_detector=e.supports_detector,
                supports_product=e.supports_product,
                supports_satellite=e.supports_satellite,
                supports_level=e.supports_level,
                wavelengths=list(e.wavelengths),
                products=list(e.products),
                levels=list(e.levels),
                default_wavelength=e.default_wavelength,
                default_product=e.default_product,
                default_level=e.default_level,
                default_satellite=e.default_satellite,
            )
        )
    return out


def _lookup_observable(key: str) -> Any:
    for e in archive.INSTRUMENT_REGISTRY:
        if e.key == key:
            return e
    return None


# ── search ──────────────────────────────────────────────────────────────────────

# The raw Fido response is heavy and not JSON-serialisable, so it is kept in
# process keyed by an opaque search_id; the follow-up fetch loads it to download
# exactly the selected rows (mirrors the desktop SunPySearchResult flow).
_SEARCH_CACHE: "OrderedDict[str, SunPySearchResult]" = OrderedDict()
_SEARCH_CACHE_MAX = 32
_SEARCH_LOCK = threading.Lock()


def _cache_search(result: SunPySearchResult) -> str:
    sid = uuid4().hex
    with _SEARCH_LOCK:
        _SEARCH_CACHE[sid] = result
        _SEARCH_CACHE.move_to_end(sid)
        while len(_SEARCH_CACHE) > _SEARCH_CACHE_MAX:
            _SEARCH_CACHE.popitem(last=False)
    return sid


def _get_search(search_id: str) -> SunPySearchResult:
    with _SEARCH_LOCK:
        result = _SEARCH_CACHE.get(search_id)
        if result is None:
            raise KeyError(search_id)
        _SEARCH_CACHE.move_to_end(search_id)
        return result


def _naive_utc(dt: datetime) -> datetime:
    """astropy Time rejects tz-aware ISO strings; normalise to naive UTC."""
    return dt.astimezone(timezone.utc).replace(tzinfo=None) if dt.tzinfo else dt


def _spec_from_request(req: SearchRequest) -> SunPyQuerySpec:
    entry = _lookup_observable(req.observable)
    if entry is None:
        raise ValueError(f"Unknown observable: {req.observable}")
    return SunPyQuerySpec(
        start_dt=_naive_utc(req.start),
        end_dt=_naive_utc(req.end),
        spacecraft=entry.spacecraft,
        instrument=entry.instrument,
        detector=entry.detector,
        wavelength_angstrom=(req.wavelength_angstrom if entry.supports_wavelength else None),
        satellite_number=(req.satellite_number or entry.default_satellite),
        sample_seconds=req.sample_seconds,
        max_records=int(req.max_records or 60),
        product=(req.product or entry.default_product) if entry.supports_product else None,
        level=(req.level or entry.default_level) if entry.supports_level else None,
    )


def _rows_dto(result: SunPySearchResult) -> list[SearchRow]:
    return [
        SearchRow(
            index=i,
            start=r.start,
            end=r.end,
            source=r.source,
            provider=r.provider,
            instrument=r.instrument,
            size=r.size,
            fileid=r.fileid,
        )
        for i, r in enumerate(result.rows)
    ]


def run_search(req: SearchRequest) -> SearchResponse:
    spec = _spec_from_request(req)
    result = archive.search(spec, allow_time_fallback=True)
    sid = _cache_search(result)
    return SearchResponse(
        search_id=sid,
        observable=req.observable,
        data_kind=result.data_kind,
        rows=_rows_dto(result),
        notice=result.notice,
    )


def run_find_latest(req: SearchRequest) -> SearchResponse:
    spec = _spec_from_request(req)
    result = archive.find_latest_search(spec)
    if result is None or not result.rows:
        return SearchResponse(
            search_id="",
            observable=req.observable,
            data_kind="map",
            rows=[],
            notice="No recent data was found within the archive lookback window.",
        )
    sid = _cache_search(result)
    return SearchResponse(
        search_id=sid,
        observable=req.observable,
        data_kind=result.data_kind,
        rows=_rows_dto(result),
        notice=result.notice,
    )


# ── fetch selected rows → session (background job) ───────────────────────────────


def _download_url(url: str, dest: Path, *, retries: int = 3, timeout: int = 180) -> Path:
    """Stream one JSOC segment URL to ``dest`` (retried; stdlib urllib)."""
    from urllib.request import Request, urlopen

    last: Exception | None = None
    for _attempt in range(retries):
        try:
            req = Request(url, headers={"User-Agent": "SolarMonitoringDashboard/0.1"})
            with urlopen(req, timeout=timeout) as resp, open(dest, "wb") as fh:
                shutil.copyfileobj(resp, fh)
            if dest.exists() and dest.stat().st_size > 0:
                return dest
        except Exception as exc:  # noqa: BLE001 - retry transient mirror errors
            last = exc
    raise last or OSError(f"Download failed: {url}")


def _download_jsoc(
    result: SunPySearchResult,
    sel: list[int],
    frame_size: str,
    cutout: tuple[float, float, float, float],
    sdir: Path,
    progress: Callable[[float, str], None] | None,
) -> list[Path]:
    spec = result.spec
    rows = result.rows
    start = min(rows[i].start for i in sel)
    end = max(rows[i].end for i in sel)
    if end <= start:
        end = start + timedelta(seconds=12)

    proc = jsoc.size_process(frame_size, cutout=cutout) if frame_size != "full" else None
    common = dict(
        start=start,
        end=end,
        email=settings.jsoc_email,
        cadence_seconds=spec.sample_seconds,
        process=proc,
    )
    if str(spec.instrument or "").upper() == "HMI":
        # HMI "as-is" segments are raw SUMS files with NO header keywords (they
        # live in DRMS), so sunpy can't build a Map from them. A staged
        # protocol="fits" export merges the keywords into the files.
        export = jsoc.export_urls(
            product=str(spec.product or "magnetogram"),
            method="url", protocol="fits", **common,
        )
    else:
        # AIA lev1 segments embed full headers — keep the quick as-is path.
        export = jsoc.export_urls(
            wavelength_angstrom=(spec.wavelength_angstrom or 193.0), **common
        )

    files: list[Path] = []
    n = len(export.urls)
    if n == 0:
        raise ValueError("JSOC returned no records for the selected window.")
    for k, entry in enumerate(export.urls):
        dest = sdir / f"_jsoc_{k:03d}.fits"
        _download_url(entry.url, dest)
        files.append(dest)
        if progress:
            progress(0.1 + 0.7 * (k + 1) / n, f"Downloaded {k + 1}/{n} frame(s) via JSOC")
    return files


def _download_vso(
    result: SunPySearchResult,
    sel: list[int],
    sdir: Path,
    progress: Callable[[float, str], None] | None,
) -> list[Path]:
    from sunpy.net import Fido

    raw = result.raw_response
    index_map = result.row_index_map
    files: list[Path] = []
    n = len(sel)
    for k, i in enumerate(sel):
        try:
            block, row = index_map[i]
            sub = raw[block, row]
        except Exception:  # noqa: BLE001 - fall back to fetching the whole result
            sub = raw
        res = Fido.fetch(sub, path=str(sdir / "{file}"), progress=False)
        attempts = 1
        while getattr(res, "errors", None) and attempts < 3:
            attempts += 1
            res = Fido.fetch(res, progress=False)
        files.extend(Path(f) for f in res)
        if progress:
            progress(0.1 + 0.7 * (k + 1) / n, f"Downloaded {k + 1}/{n} frame(s) via VSO")
        if sub is raw:  # fetched the whole result in one shot
            break
    # De-duplicate while preserving order (a whole-result fetch may repeat files).
    return list(dict.fromkeys(files))


def _download_selection(
    result: SunPySearchResult,
    sel: list[int],
    source: str,
    frame_size: str,
    cutout: tuple[float, float, float, float],
    sdir: Path,
    progress: Callable[[float, str], None] | None,
) -> list[Path]:
    spec = result.spec
    is_sdo = str(spec.spacecraft or "").upper() == "SDO" and str(
        spec.instrument or ""
    ).upper() in ("AIA", "HMI")
    have_email = bool(settings.jsoc_email)

    if source == "jsoc":
        if not is_sdo:
            raise ValueError("The JSOC fast path is only available for SDO/AIA and SDO/HMI.")
        if not have_email:
            raise ValueError(
                "The JSOC fast path needs a registered notify e-mail (set JSOC_EMAIL). "
                "Use source 'vso' instead."
            )
        return _download_jsoc(result, sel, frame_size, cutout, sdir, progress)

    if source == "auto" and is_sdo and have_email:
        try:
            return _download_jsoc(result, sel, frame_size, cutout, sdir, progress)
        except Exception as exc:  # noqa: BLE001 - fall back to VSO on any JSOC failure
            logger.info("JSOC fast path failed; falling back to VSO: %s", exc)
            if progress:
                progress(0.1, "JSOC unavailable — falling back to VSO…")

    return _download_vso(result, sel, sdir, progress)


def fetch_selected_job(
    search_id: str,
    indices: list[int],
    source: str,
    frame_size: str,
    cutout: tuple[float, float, float, float],
    *,
    progress: Callable[[float, str], None] | None = None,
) -> tuple[str, dict]:
    """Download the selected search rows into a new session (job function).

    Returns ``(session_dir, meta)`` where ``meta['session']`` is the built session
    so ``/jobs/{id}`` hands it back to the client (mirrors ``fetch_via_fido``).
    """
    try:
        result = _get_search(search_id)
    except KeyError:
        raise ValueError("Search expired — run the search again before downloading.")

    if result.data_kind != archive.DATA_KIND_MAP:
        raise ValueError("This observable returns timeseries data, which the image workbench can't display.")

    rows = result.rows
    sel = [i for i in (indices or list(range(len(rows)))) if 0 <= i < len(rows)]
    if not sel:
        raise ValueError("No rows selected to download.")

    def _p(frac: float, msg: str = "") -> None:
        if progress:
            progress(frac, msg)

    _p(0.05, f"Downloading {len(sel)} frame(s)…")
    session_id = uuid4().hex
    sdir = data.session_dir(session_id)
    sdir.mkdir(parents=True, exist_ok=True)
    try:
        files = _download_selection(result, sel, source, frame_size, cutout, sdir, progress)
        if not files:
            raise ValueError("No files were downloaded for the selection.")
        _p(0.85, "Building session…")
        session = data.build_session(session_id, "search", files)
        for f in files:  # build_session copied to frame_NNN.fits; drop originals
            f.unlink(missing_ok=True)
    except Exception:
        data._rmtree(sdir)
        raise
    _p(1.0, "Done")
    return str(sdir), {"kind": "session", "session": session.model_dump(mode="json")}
