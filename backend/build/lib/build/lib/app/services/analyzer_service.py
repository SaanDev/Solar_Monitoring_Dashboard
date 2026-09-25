"""e-CALLISTO Analyzer service.

Holds uploaded / archive-imported FITS server-side keyed by an opaque id (a file
under ``settings.analyzer_dir``), and re-renders the dynamic spectrum on demand as
the user changes controls. Reuses the existing FITS loader, processing, and PNG
renderer; rendered PNGs are cached by a hash of the render parameters.
"""
from __future__ import annotations

import hashlib
import io
import json
import re
import time
from collections import OrderedDict
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import numpy as np
from astropy.io import fits

from app.config import settings
from app.processing.analyzer_combine import (
    CombineInput,
    combine_frequency,
    combine_time,
)
from app.processing.analyzer_processing import (
    COLORMAPS,
    default_limits,
    process_spectrum,
    resolve_cmap,
)
from app.processing.analysis_session import (
    from_legacy_max_intensity,
    normalize_session,
    to_project_payload,
)
from app.processing.dynamic_spectrum import parse_obs_start
from app.processing.efaproj import read_project, write_project
from app.processing.fits_loader import FitsData, load_ecallisto_fits
from app.processing.plot_rendering import (
    render_extra_plot,
    render_fit_plot,
    render_shock_spectrogram,
    render_spectrum_png,
    shock_geometry as _shock_geometry_dict,
)
from app.processing.shock_analysis import (
    compute_shock_parameters,
    extract_max_intensity,
    power_law_fit,
)
from app.schemas.analyzer_schema import (
    AnalyzerSession,
    AnalyzerStats,
    ProjectSettings,
    ShockSession,
)
from app.services.ecallisto_service import get_archive_fits

_ID_RE = re.compile(r"^[0-9a-f]{32}$")
# FITS structural keys astropy manages itself; don't copy them onto a new HDU.
_SKIP_HEADER_KEYS = {
    "SIMPLE", "BITPIX", "EXTEND", "BSCALE", "BZERO", "BLANK",
    "NAXIS", "NAXIS1", "NAXIS2", "NAXIS3", "PCOUNT", "GCOUNT",
}


@dataclass(frozen=True)
class RenderParams:
    method: str = "median"
    intensity_unit: str = "db"
    time_unit: str = "seconds"
    cmap: str = "magma"
    vmin: float | None = None
    vmax: float | None = None
    rfi_enabled: bool = False
    rfi_low: float = 1.0
    rfi_high: float = 99.0
    station: str = ""


# ── Storage / sessions ───────────────────────────────────────────────────────


def _safe_id(id: str) -> str:
    if not _ID_RE.match(id or ""):
        raise ValueError("Invalid analyzer id")
    return id


# FITS suffixes stored per session; excludes the ``{id}.analysis.json`` shock sidecar.
_FITS_SUFFIXES = {".fits", ".fit", ".gz"}


def _locate(id: str) -> Path:
    """Resolve the stored FITS for ``id`` within analyzer_dir (path-traversal safe)."""
    _safe_id(id)
    base = Path(settings.analyzer_dir).resolve()
    for p in base.glob(f"{id}.*"):
        rp = p.resolve()
        if rp.is_file() and base in rp.parents and rp.suffix.lower() in _FITS_SUFFIXES:
            return rp
    raise FileNotFoundError(f"No FITS for analyzer id {id}")


def _station_from(header: dict, fallback: str) -> str:
    if fallback:
        return fallback
    for key in ("INSTRUME", "CONTENT", "ORIGIN"):
        val = header.get(key)
        if val:
            return str(val).strip()
    return "UNKNOWN"


def _build_session(id: str, path: Path, station: str, filename: str) -> AnalyzerSession:
    fd = load_ecallisto_fits(path)
    obs = parse_obs_start(fd.header)
    t = fd.time_axis
    duration = float(t[-1] - t[0]) if t.size else 0.0
    return AnalyzerSession(
        id=id,
        station=_station_from(fd.header, station),
        filename=filename,
        n_freq=int(fd.data.shape[0]),
        n_time=int(fd.data.shape[1]),
        freq_min_mhz=float(np.nanmin(fd.freq_axis)),
        freq_max_mhz=float(np.nanmax(fd.freq_axis)),
        start_time=obs,
        end_time=(obs + timedelta(seconds=duration)) if obs else None,
        duration_s=duration,
    )


def store_upload(content: bytes, filename: str, station: str = "") -> AnalyzerSession:
    """Persist an uploaded FITS and return its session metadata."""
    cleanup_stale()
    id = uuid4().hex
    ext = ".fit.gz" if filename.lower().endswith(".gz") else ".fits"
    path = Path(settings.analyzer_dir) / f"{id}{ext}"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    try:
        return _build_session(id, path, station, filename)
    except Exception:
        path.unlink(missing_ok=True)
        raise


async def store_from_archive(d: date, station: str, filename: str) -> AnalyzerSession | None:
    """Pull a file from the e-CALLISTO archive into an analyzer session."""
    result = await get_archive_fits(d, station, filename)
    if result is None:
        return None
    content, name = result
    return store_upload(content, name, station)


# ── Combine (time / frequency) ───────────────────────────────────────────────


def _write_ecallisto_fits(
    path: Path,
    data: np.ndarray,
    freq_axis: np.ndarray,
    time_axis: np.ndarray,
    obs_start: datetime | None,
    station: str,
) -> None:
    """Write an e-CALLISTO-style FITS (Primary data + TIME/FREQUENCY table) so it
    reloads like any other session — used for combine results and opened projects."""
    data = np.asarray(data, dtype=np.float32)
    n_freq, n_time = data.shape
    prim = fits.PrimaryHDU(data)
    if obs_start is not None:
        prim.header["DATE-OBS"] = obs_start.strftime("%Y/%m/%d")
        prim.header["TIME-OBS"] = obs_start.strftime("%H:%M:%S.%f")[:-3]
    prim.header["FRQMIN"] = float(np.nanmin(freq_axis))
    prim.header["FRQMAX"] = float(np.nanmax(freq_axis))
    prim.header["CONTENT"] = station
    tcol = fits.Column(
        name="TIME", format=f"{n_time}E",
        array=np.asarray(time_axis, dtype=np.float32).reshape(1, n_time),
    )
    fcol = fits.Column(
        name="FREQUENCY", format=f"{n_freq}E",
        array=np.asarray(freq_axis, dtype=np.float32).reshape(1, n_freq),
    )
    fits.HDUList([prim, fits.BinTableHDU.from_columns([tcol, fcol])]).writeto(path)


def combine(ids: list[str], mode: str) -> AnalyzerSession:
    """Combine several sessions in time or frequency into a new session."""
    if len(ids) < 2:
        raise ValueError("Select at least 2 files to combine.")
    inputs: list[CombineInput] = []
    first_station = ""
    for i, sid in enumerate(ids):
        fd = load_ecallisto_fits(_locate(sid))
        if i == 0:
            first_station = _station_from(fd.header, "")
        inputs.append(CombineInput(fd.data, fd.freq_axis, fd.time_axis, parse_obs_start(fd.header)))

    if mode == "time":
        res = combine_time(inputs)
    elif mode == "frequency":
        res = combine_frequency(inputs)
    else:
        raise ValueError("mode must be 'time' or 'frequency'")

    cleanup_stale()
    new_id = uuid4().hex
    label = f"{first_station or 'COMBINED'} - {mode}-combined x{len(ids)}"
    path = Path(settings.analyzer_dir) / f"{new_id}.fits"
    path.parent.mkdir(parents=True, exist_ok=True)
    _write_ecallisto_fits(path, res.data, res.freq_axis, res.time_axis, res.obs_start, label)
    try:
        return _build_session(new_id, path, label, f"{mode}_combined_{len(ids)}files.fits")
    except Exception:
        path.unlink(missing_ok=True)
        raise


# ── Processing / render / export ─────────────────────────────────────────────


# Cache the processed array keyed by the params that change the data distribution
# (not vmin/vmax/cmap/time_unit), so dragging the display sliders re-runs only the
# cheap matplotlib render — keeping the live preview responsive.
_ProcEntry = tuple  # (time_axis, freq_axis, obs_start, arr, label)
_PROC_CACHE: "OrderedDict[tuple, _ProcEntry]" = OrderedDict()
_PROC_CACHE_MAX = 8


def _proc_key(id: str, params: RenderParams) -> tuple:
    return (id, params.method, params.intensity_unit, params.rfi_enabled, params.rfi_low, params.rfi_high)


def _processed(id: str, params: RenderParams) -> _ProcEntry:
    """(time_axis, freq_axis, obs_start, processed_array, cbar_label), memoized."""
    key = _proc_key(id, params)
    hit = _PROC_CACHE.get(key)
    if hit is not None:
        _PROC_CACHE.move_to_end(key)
        return hit
    fd = load_ecallisto_fits(_locate(id))
    arr, label = process_spectrum(
        fd.data,
        intensity_unit=params.intensity_unit,
        method=params.method,
        rfi_enabled=params.rfi_enabled,
        rfi_low=params.rfi_low,
        rfi_high=params.rfi_high,
    )
    entry = (fd.time_axis, fd.freq_axis, parse_obs_start(fd.header), arr, label)
    _PROC_CACHE[key] = entry
    _PROC_CACHE.move_to_end(key)
    while len(_PROC_CACHE) > _PROC_CACHE_MAX:
        _PROC_CACHE.popitem(last=False)
    return entry


def compute_stats(id: str, params: RenderParams) -> AnalyzerStats:
    """Processed-data min/max and default vmin/vmax for the display sliders."""
    _t, _f, _o, arr, _label = _processed(id, params)
    finite = arr[np.isfinite(arr)]
    data_min = float(finite.min()) if finite.size else 0.0
    data_max = float(finite.max()) if finite.size else 1.0
    if params.vmin is None or params.vmax is None:
        vmin, vmax = default_limits(arr, params.intensity_unit)
    else:
        vmin, vmax = params.vmin, params.vmax
    return AnalyzerStats(data_min=data_min, data_max=data_max, vmin=float(vmin), vmax=float(vmax))


# Live preview renders at a crisp-but-fast DPI; downloads render extra-sharp.
RENDER_DPI = 200
EXPORT_DPI = 260


def _param_hash(id: str, params: RenderParams, dpi: int) -> str:
    raw = repr((id, params, dpi)).encode()
    return hashlib.sha1(raw).hexdigest()[:12]


def render(id: str, params: RenderParams, dpi: int = RENDER_DPI) -> Path:
    """Render (or reuse a cached) PNG for the given params; returns the PNG path."""
    out = Path(settings.spectra_dir) / f"analyzer_{id}_{_param_hash(id, params, dpi)}.png"
    if out.exists():
        return out
    time_axis, freq_axis, obs_start, arr, label = _processed(id, params)
    if params.vmin is None or params.vmax is None:
        vmin, vmax = default_limits(arr, params.intensity_unit)
    else:
        vmin, vmax = params.vmin, params.vmax
    render_spectrum_png(
        arr,
        time_axis,
        freq_axis,
        out,
        station=params.station,
        obs_start=obs_start,
        vmin=float(vmin),
        vmax=float(vmax),
        cmap=resolve_cmap(params.cmap),
        cbar_label=label,
        time_unit=params.time_unit,
        dpi=dpi,
    )
    return out


def export_fits(id: str, params: RenderParams) -> tuple[bytes, str]:
    """Background-subtracted data as a new FITS file (bytes, filename)."""
    _t, _f, _o, arr, _label = _processed(id, params)
    fd = load_ecallisto_fits(_locate(id))  # original header (not on the live path)
    hdu = fits.PrimaryHDU(arr.astype(np.float32))
    for key, value in fd.header.items():
        if key in _SKIP_HEADER_KEYS or not key:
            continue
        try:
            hdu.header[key] = value
        except Exception:
            continue
    hdu.header["BGSUB"] = params.method
    hdu.header["INTUNIT"] = params.intensity_unit
    hdu.header.add_history(
        f"Background-subtracted (method={params.method}, unit={params.intensity_unit}) "
        "via Solar Dashboard e-CALLISTO Analyzer"
    )
    buf = io.BytesIO()
    fits.HDUList([hdu]).writeto(buf)
    return buf.getvalue(), f"analyzer_{id[:8]}_{params.intensity_unit}.fits"


# ── Type II shock analysis (Path A) ──────────────────────────────────────────

SHOCK_RENDER_DPI = 150


def _analysis_path(id: str) -> Path:
    """Sidecar JSON holding the shock-analysis session for ``id`` (max-intensity
    points + fit + shock summary). Lives beside the FITS so cleanup_stale sweeps it."""
    return Path(settings.analyzer_dir) / f"{_safe_id(id)}.analysis.json"


def _load_analysis(id: str) -> dict | None:
    p = _analysis_path(id)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def _save_analysis(id: str, sidecar: dict) -> None:
    p = _analysis_path(id)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(sidecar), encoding="utf-8")


def _analysis_hash(id: str) -> str:
    """Short hash of the sidecar contents for cache-busting derived plots/exports."""
    p = _analysis_path(id)
    raw = p.read_bytes() if p.exists() else b""
    return hashlib.sha1(raw).hexdigest()[:12]


def shock_geometry(id: str, params: RenderParams) -> dict:
    """Plotted-area geometry for the current spectrogram (for the browser lasso)."""
    time_axis, freq_axis, _o, _arr, _label = _processed(id, params)
    return _shock_geometry_dict(time_axis, freq_axis, SHOCK_RENDER_DPI)


def render_shock(id: str, params: RenderParams, dpi: int = SHOCK_RENDER_DPI) -> Path:
    """Render (or reuse) the fixed-axes shock spectrogram PNG for lasso overlay."""
    out = Path(settings.spectra_dir) / f"shock_{id}_{_param_hash(id, params, dpi)}.png"
    if out.exists():
        return out
    time_axis, freq_axis, obs_start, arr, _label = _processed(id, params)
    if params.vmin is None or params.vmax is None:
        vmin, vmax = default_limits(arr, params.intensity_unit)
    else:
        vmin, vmax = params.vmin, params.vmax
    render_shock_spectrogram(
        arr, time_axis, freq_axis, out,
        station=params.station, obs_start=obs_start,
        vmin=float(vmin), vmax=float(vmax), cmap=resolve_cmap(params.cmap),
        time_unit=params.time_unit, dpi=dpi,
    )
    return out


def compute_max_intensity(
    id: str,
    params: RenderParams,
    polygon: list[tuple[float, float]] | None,
    auto_clean: bool = True,
) -> dict:
    """Isolate the burst (polygon in data coords) and extract per-column peak frequency."""
    _t, _f, _o, arr, _label = _processed(id, params)
    time_axis, freq_axis = _t, _f
    return extract_max_intensity(arr, time_axis, freq_axis, polygon=polygon, auto_clean=auto_clean)


def _fit_equation(fit: dict) -> str:
    return f"f(x) = {fit['a']:.2f} · x^-{abs(fit['b']):.2f}"


def fit_shock(
    id: str,
    points: list[tuple[float, float]],
    fold: int,
    harmonic: bool,
    time_channels: list[float] | None = None,
) -> dict:
    """Power-law fit + Newkirk shock parameters on the kept points; persist a sidecar."""
    _safe_id(id)
    if len(points) < 2:
        raise ValueError("At least two maximum-intensity points are required to fit.")
    times = [float(p[0]) for p in points]
    freqs = [float(p[1]) for p in points]

    fit = power_law_fit(times, freqs)
    result = compute_shock_parameters(fit, times, freqs, fold=fold, harmonic=harmonic)

    if time_channels is not None and len(time_channels) == len(points):
        channels = [float(c) for c in time_channels]
    else:
        channels = [float(i) for i in range(len(points))]

    sidecar = {
        "max_intensity": {
            "time_channels": channels,
            "time_seconds": times,
            "freqs": freqs,
            "fundamental": bool(not harmonic),
            "harmonic": bool(harmonic),
        },
        "analyzer": {
            "fit_params": fit,
            "fold": int(max(1, min(4, fold))),
            "shock_summary": result["shock_summary"],
        },
        "curves": result["curves"],
        "fit_line": result["fit_line"],
        "equation": _fit_equation(fit),
    }
    _save_analysis(id, sidecar)

    return {
        "fit": fit,
        "shock_summary": result["shock_summary"],
        "curves": result["curves"],
        "fit_line": result["fit_line"],
    }


def render_shock_fit_png(id: str) -> Path:
    """Scatter of the kept max-intensity points + best-fit overlay."""
    sidecar = _load_analysis(id)
    if sidecar is None:
        raise FileNotFoundError(f"No shock analysis for id {id}")
    out = Path(settings.spectra_dir) / f"shockfit_{id}_{_analysis_hash(id)}.png"
    if out.exists():
        return out
    mi = sidecar.get("max_intensity") or {}
    fit_line = sidecar.get("fit_line") or {}
    render_fit_plot(
        out,
        np.asarray(mi.get("time_seconds") or [], dtype=float),
        np.asarray(mi.get("freqs") or [], dtype=float),
        fit_time=np.asarray(fit_line.get("time_s") or [], dtype=float),
        fit_freq=np.asarray(fit_line.get("freq_mhz") or [], dtype=float),
        title="Power-law best fit",
        equation=sidecar.get("equation", ""),
    )
    return out


def render_shock_extra_png(id: str, kind: str) -> Path:
    """Derived shock plot (speed-vs-height / speed-vs-freq / height-vs-freq)."""
    sidecar = _load_analysis(id)
    if sidecar is None:
        raise FileNotFoundError(f"No shock analysis for id {id}")
    out = Path(settings.spectra_dir) / f"shockextra_{id}_{kind}_{_analysis_hash(id)}.png"
    if out.exists():
        return out
    render_extra_plot(out, kind, sidecar.get("curves") or {})
    return out


# Shock-summary rows for the exported table (label, summary-key, error-key, unit, digits).
_SHOCK_EXPORT_ROWS = [
    ("Average Frequency", "avg_freq_mhz", "avg_freq_err_mhz", "MHz", 2),
    ("Average Drift Rate", "avg_drift_mhz_s", "avg_drift_err_mhz_s", "MHz/s", 4),
    ("Starting Frequency", "start_freq_mhz", "start_freq_err_mhz", "MHz", 2),
    ("Initial Shock Speed", "initial_shock_speed_km_s", "initial_shock_speed_err_km_s", "km/s", 2),
    ("Initial Shock Height", "initial_shock_height_rs", "initial_shock_height_err_rs", "Rs", 3),
    ("Average Shock Speed", "avg_shock_speed_km_s", "avg_shock_speed_err_km_s", "km/s", 2),
    ("Average Shock Height", "avg_shock_height_rs", "avg_shock_height_err_rs", "Rs", 3),
]


def _shock_export_rows(id: str) -> tuple[dict, list[list]]:
    sidecar = _load_analysis(id)
    if sidecar is None:
        raise FileNotFoundError(f"No shock analysis for id {id}")
    analyzer = sidecar.get("analyzer") or {}
    summary = analyzer.get("shock_summary") or {}
    fit = analyzer.get("fit_params") or {}
    rows: list[list] = [["Parameter", "Value", "Error", "Unit"]]
    for label, key, ekey, unit, digits in _SHOCK_EXPORT_ROWS:
        val = summary.get(key)
        err = summary.get(ekey)
        rows.append([
            label,
            round(float(val), digits) if val is not None else "",
            round(float(err), digits) if err is not None else "",
            unit,
        ])
    rows.append(["Newkirk fold", summary.get("fold", analyzer.get("fold", 1)), "", ""])
    rows.append(["Emission", "Harmonic" if summary.get("harmonic") else "Fundamental", "", ""])
    if fit:
        rows.append(["Fit a", round(float(fit.get("a", 0)), 4), "", ""])
        rows.append(["Fit b", round(float(fit.get("b", 0)), 4), "", ""])
        rows.append(["R²", round(float(fit.get("r2", 0)), 4), "", ""])
        rows.append(["RMSE", round(float(fit.get("rmse", 0)), 4), "", ""])
    return summary, rows


def export_shock_table(id: str, fmt: str) -> tuple[bytes, str]:
    """Shock parameters as CSV or Excel (bytes, filename). Excel needs openpyxl."""
    _summary, rows = _shock_export_rows(id)
    if fmt == "csv":
        import csv
        buf = io.StringIO()
        csv.writer(buf).writerows(rows)
        return buf.getvalue().encode("utf-8"), f"shock_{id[:8]}.csv"
    if fmt == "xlsx":
        try:
            from openpyxl import Workbook
        except ImportError as exc:
            raise ValueError(
                "Excel export needs the 'openpyxl' package (rebuild the backend image)."
            ) from exc
        wb = Workbook()
        ws = wb.active
        ws.title = "Shock Parameters"
        for row in rows:
            ws.append(row)
        for cell in ws[1]:
            cell.font = cell.font.copy(bold=True)
        buf = io.BytesIO()
        wb.save(buf)
        return buf.getvalue(), f"shock_{id[:8]}.xlsx"
    raise ValueError("format must be 'csv' or 'xlsx'")


def _shock_session_from_normalized(norm: dict | None) -> ShockSession | None:
    """Build the frontend-facing ShockSession from a normalized analysis session."""
    if not norm:
        return None
    mi = dict(norm.get("max_intensity") or {})
    an = dict(norm.get("analyzer") or {})
    freqs = mi.get("freqs")
    if freqs is None:
        return None
    time_seconds = mi.get("time_seconds")
    if time_seconds is None:
        time_seconds = mi.get("time_channels")
    return ShockSession(
        time_seconds=[float(x) for x in np.asarray(time_seconds, dtype=float).reshape(-1)],
        freqs=[float(x) for x in np.asarray(freqs, dtype=float).reshape(-1)],
        fundamental=bool(mi.get("fundamental", True)),
        harmonic=bool(mi.get("harmonic", False)),
        fold=int(an.get("fold", 1)),
        fit=an.get("fit_params"),
        shock_summary=an.get("shock_summary"),
    )


def _sidecar_from_normalized(norm: dict) -> dict:
    """Sidecar dict (JSON-safe) from a normalized analysis session — for open_project."""
    mi = dict(norm.get("max_intensity") or {})
    an = dict(norm.get("analyzer") or {})

    def _list(v):
        return None if v is None else [float(x) for x in np.asarray(v, dtype=float).reshape(-1)]

    return {
        "max_intensity": {
            "time_channels": _list(mi.get("time_channels")),
            "time_seconds": _list(mi.get("time_seconds")),
            "freqs": _list(mi.get("freqs")),
            "fundamental": bool(mi.get("fundamental", True)),
            "harmonic": bool(mi.get("harmonic", False)),
        },
        "analyzer": {
            "fit_params": an.get("fit_params"),
            "fold": int(an.get("fold", 1)),
            "shock_summary": an.get("shock_summary"),
        },
    }


def _embed_analysis_session(
    id: str, meta: dict, arrays: dict, fd: FitsData, station: str
) -> None:
    """If a shock-analysis sidecar exists, write meta['analysis_session'] + arrays and the
    legacy max_intensity mirror — byte-compatible with the desktop project format."""
    sidecar = _load_analysis(id)
    if sidecar is None:
        return
    mi = dict(sidecar.get("max_intensity") or {})
    analyzer = dict(sidecar.get("analyzer") or {})
    if not mi.get("freqs"):
        return

    session = {
        "source": {
            "filename": station,
            "shape": [int(fd.data.shape[0]), int(fd.data.shape[1])],
        },
        "max_intensity": mi,
        "analyzer": analyzer,
        "ui": {"restore_max_window": True, "restore_analyzer_window": True},
    }
    session_meta, session_arrays = to_project_payload(session)
    if session_meta is None:
        return
    meta["analysis_session"] = session_meta
    arrays.update(session_arrays)

    # Legacy compatibility payload (older desktop builds read meta['max_intensity']).
    meta["max_intensity"] = {
        "present": True,
        "fundamental": bool(mi.get("fundamental", True)),
        "harmonic": bool(mi.get("harmonic", False)),
        "analyzer": analyzer,
    }
    if mi.get("time_channels") is not None:
        arrays["max_time_channels"] = np.asarray(mi.get("time_channels"), dtype=float)
    if mi.get("time_seconds") is not None:
        arrays["max_time_seconds"] = np.asarray(mi.get("time_seconds"), dtype=float)
    if mi.get("freqs") is not None:
        arrays["max_freqs"] = np.asarray(mi.get("freqs"), dtype=float)


# ── Project (.efaproj) save / open — interoperable with the desktop app ───────


def _cmap_to_desktop(name: str) -> str:
    return "Custom" if name == "custom" else name


def _cmap_from_desktop(name: str) -> str:
    n = (name or "").strip()
    if n.lower() == "custom":
        return "custom"
    return n if n in COLORMAPS else ("magma" if n.lower() not in COLORMAPS else n.lower())


def _opt_float(value) -> float | None:
    try:
        return None if value is None else float(value)
    except (TypeError, ValueError):
        return None


def _header_text(path: Path) -> str | None:
    try:
        with fits.open(path) as hdul:
            return hdul[0].header.tostring(sep="\n", endcard=True, padding=False)
    except Exception:
        return None


def save_project(id: str, params: RenderParams) -> tuple[bytes, str]:
    """Serialize the session as a .efaproj (desktop-compatible). Returns bytes+name."""
    fd = load_ecallisto_fits(_locate(id))
    time_axis, freq_axis, obs_start, arr, _label = _processed(id, params)
    if params.vmin is None or params.vmax is None:
        vmin, vmax = default_limits(arr, params.intensity_unit)
    else:
        vmin, vmax = params.vmin, params.vmax

    ut_start_sec = None
    if obs_start is not None:
        ut_start_sec = (
            obs_start.hour * 3600 + obs_start.minute * 60
            + obs_start.second + obs_start.microsecond / 1e6
        )
    step = float(np.median(np.abs(np.diff(freq_axis)))) if np.asarray(freq_axis).size > 1 else None
    station = params.station or _station_from(fd.header, "") or "web-project"

    meta = {
        "filename": station,
        "current_plot_type": "Background Subtracted",
        "noise_reduced_original_plot_type": "Background Subtracted",
        "lower_slider": 0,
        "upper_slider": 100,
        "noise_clip_low": float(vmin),
        "noise_clip_high": float(vmax),
        "noise_clip_scale": "linear",
        "use_db": params.intensity_unit == "db",
        "use_utc": params.time_unit == "utc",
        "ut_start_sec": ut_start_sec,
        "cmap": _cmap_to_desktop(params.cmap),
        "frequency_step_mhz": step,
        "view": None,
        "noise_vmin": float(vmin),
        "noise_vmax": float(vmax),
        "fits_header": _header_text(_locate(id)),
        "fits_source_path": None,
        "is_combined": False,
        "combined_mode": None,
        "combined_sources": [],
        "graph": {
            "remove_titles": False, "title_bold": False, "title_italic": False,
            "axis_bold": False, "axis_italic": False, "ticks_bold": False,
            "ticks_italic": False, "title_override": "", "font_family": "",
            "tick_font_px": 11, "axis_label_font_px": 12, "title_font_px": 14,
        },
        "rfi": {},
        "annotations": [],
        "origin": "solar-dashboard-web-analyzer",
    }
    arrays = {
        "raw_data": np.asarray(fd.data, dtype=np.float32),
        "noise_reduced_data": np.asarray(arr, dtype=np.float32),
        "noise_reduced_original": np.asarray(arr, dtype=np.float32),
        "freqs": np.asarray(freq_axis, dtype=np.float32),
        "time": np.asarray(time_axis, dtype=np.float32),
    }

    # Embed the shock-analysis session so the project round-trips with the desktop app
    # (meta["analysis_session"] + analysis_* arrays, plus the legacy max_intensity mirror).
    _embed_analysis_session(id, meta, arrays, fd, station)

    buf = io.BytesIO()
    write_project(buf, meta=meta, arrays=arrays)
    date_tag = obs_start.strftime("%Y%m%d") if obs_start else "session"
    return buf.getvalue(), f"{station}_{date_tag}.efaproj"


def open_project(content: bytes) -> tuple[AnalyzerSession, ProjectSettings, ShockSession | None]:
    """Load a .efaproj (desktop or web) into a new session + restorable settings +
    any restored shock-analysis session."""
    payload = read_project(io.BytesIO(content))
    meta, arrays = payload.meta, payload.arrays

    raw = arrays.get("raw_data")
    if raw is None:
        raw = arrays.get("noise_reduced_data")
    freqs = arrays.get("freqs")
    time = arrays.get("time")
    if raw is None or freqs is None or time is None:
        raise ValueError("Project is missing spectrogram arrays (raw_data/freqs/time).")

    header: dict = {}
    htxt = meta.get("fits_header")
    if htxt:
        try:
            header = dict(fits.Header.fromstring(htxt, sep="\n"))
        except Exception:
            header = {}
    obs_start = parse_obs_start(header)
    station = _station_from(header, "") or str(meta.get("filename") or "PROJECT")

    cleanup_stale()
    new_id = uuid4().hex
    path = Path(settings.analyzer_dir) / f"{new_id}.fits"
    path.parent.mkdir(parents=True, exist_ok=True)
    _write_ecallisto_fits(
        path, np.asarray(raw, dtype=np.float32),
        np.asarray(freqs, dtype=float), np.asarray(time, dtype=float),
        obs_start, station,
    )
    try:
        session = _build_session(new_id, path, station, str(meta.get("filename") or "project.efaproj"))
    except Exception:
        path.unlink(missing_ok=True)
        raise

    settings_out = ProjectSettings(
        method="median",
        intensity_unit="db" if meta.get("use_db") else "digits",
        time_unit="utc" if meta.get("use_utc") else "seconds",
        cmap=_cmap_from_desktop(meta.get("cmap", "magma")),
        vmin=_opt_float(meta.get("noise_vmin")),
        vmax=_opt_float(meta.get("noise_vmax")),
    )

    # Restore a shock-analysis session if the project carries one (canonical or legacy).
    shock_out: ShockSession | None = None
    norm = None
    analysis_meta = meta.get("analysis_session")
    if isinstance(analysis_meta, dict):
        session_payload = dict(analysis_meta)
        max_block = dict(session_payload.get("max_intensity") or {})
        max_block["time_channels"] = arrays.get("analysis_time_channels")
        max_block["time_seconds"] = arrays.get("analysis_time_seconds")
        max_block["freqs"] = arrays.get("analysis_freqs")
        session_payload["max_intensity"] = max_block
        norm = normalize_session(session_payload)
    if norm is None:
        norm = from_legacy_max_intensity(meta, arrays)
    if norm is not None:
        try:
            _save_analysis(new_id, _sidecar_from_normalized(norm))
        except Exception:
            pass
        shock_out = _shock_session_from_normalized(norm)

    return session, settings_out, shock_out


def cleanup_stale(ttl_hours: int = 24) -> None:
    """Drop analyzer FITS + their rendered PNGs older than ``ttl_hours``."""
    cutoff = time.time() - ttl_hours * 3600
    for p in Path(settings.analyzer_dir).glob("*"):
        try:
            if p.is_file() and p.stat().st_mtime < cutoff:
                p.unlink()
        except OSError:
            pass
    for p in Path(settings.spectra_dir).glob("analyzer_*.png"):
        try:
            if p.stat().st_mtime < cutoff:
                p.unlink()
        except OSError:
            pass
