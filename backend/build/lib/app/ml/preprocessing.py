"""Preprocess raw e-CALLISTO FITS spectra into model input tensors.

Ported from the Burst Identifier project (src/preprocessing/) with the
training/batch-processing code removed — only the inference path is kept.

Pipeline per file:
  1. Read 2D [frequency, time] spectrum + metadata from the .fit.gz FITS file.
  2. Replace NaN/Inf with the finite median.
  3. Background subtraction (row-median, then Plotutil dB scale).
  4. Normalise into [0, 1] using a fixed dB window [-1, 8].
  5. Resize to the model's target shape (224×224).
  6. Return [1, H, W] float32 numpy array + metadata dict.

All numeric steps are pure NumPy — identical results on every machine.
"""
from __future__ import annotations

import math
import shutil
import tempfile
from pathlib import Path
from typing import Any

import numpy as np

# ── Raw digit → dB conversion (Plotutil Digit2Voltage / 25.4) ────────────────

PLOTUTIL_DB_SCALE = 2500.0 / 255.0 / 25.4
PLOTUTIL_DISPLAY_LIMITS = (-1.0, 8.0)


# ─── FITS reading ─────────────────────────────────────────────────────────────

def _import_fits():
    try:
        from astropy.io import fits
        return fits
    except ImportError as exc:
        raise ImportError(
            "astropy is required to read .fit.gz files. "
            "Install with: pip install astropy"
        ) from exc


def _clean_header_string(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _format_date_token(token: str | None) -> str | None:
    if token is None:
        return None
    token = token.strip()
    if len(token) == 8 and token.isdigit():
        return f"{token[0:4]}-{token[4:6]}-{token[6:8]}"
    if len(token) >= 10 and token[4] == "-" and token[7] == "-":
        return token[:10]
    return None


def _format_time_token(token: str | None) -> str | None:
    if token is None:
        return None
    token = token.strip()
    if "." in token:
        whole, frac = token.split(".", 1)
        formatted = _format_time_token(whole)
        return f"{formatted}.{frac}" if formatted else token
    if len(token) == 4 and token.isdigit():
        return f"{token[0:2]}:{token[2:4]}:00"
    if len(token) == 6 and token.isdigit():
        return f"{token[0:2]}:{token[2:4]}:{token[4:6]}"
    if len(token) >= 8 and token[2] == ":" and token[5] == ":":
        return token
    return None


def parse_filename_fallback(path: str | Path) -> dict[str, Any]:
    """Station, date, start_time from the e-CALLISTO filename."""
    path = Path(path)
    name = path.name
    stem = name[:-7] if name.endswith(".fit.gz") else path.stem
    parts = stem.split("_")
    meta: dict[str, Any] = {"station": None, "date": None, "start_time": None}
    if len(parts) >= 3:
        meta["station"] = parts[0]
        meta["date"] = _format_date_token(parts[1])
        meta["start_time"] = _format_time_token(parts[2])
    return meta


def _compute_frequency_bounds(
    header: Any, n_freq: int | None = None
) -> tuple[float | None, float | None]:
    try:
        crval = float(header.get("CRVAL2"))
        cdelt = float(header.get("CDELT2"))
    except (TypeError, ValueError):
        return None, None
    if n_freq is None:
        try:
            n_freq = int(header.get("NAXIS2"))
        except (TypeError, ValueError):
            return None, None
    if n_freq <= 0:
        return None, None
    first = crval
    last = crval + (n_freq - 1) * cdelt
    return float(min(first, last)), float(max(first, last))


def _extract_metadata(path: str | Path, hdul: Any) -> dict[str, Any]:
    fallback = parse_filename_fallback(path)
    header = hdul[0].header
    data = hdul[0].data
    shape = tuple(data.shape) if data is not None else ()
    n_freq = int(shape[-2]) if len(shape) >= 2 else None
    n_time = int(shape[-1]) if len(shape) >= 2 else None
    freq_min, freq_max = _compute_frequency_bounds(header, n_freq=n_freq)

    header_date = _format_date_token(_clean_header_string(header.get("DATE-OBS")))
    header_time = _format_time_token(_clean_header_string(header.get("TIME-OBS")))
    station = _clean_header_string(header.get("INSTRUME")) or fallback["station"]

    return {
        "station": station,
        "date": header_date or fallback["date"],
        "start_time": header_time or fallback["start_time"],
        "freq_min_mhz": freq_min,
        "freq_max_mhz": freq_max,
        "n_freq": n_freq,
        "n_time": n_time,
    }


def read_fits_spectrum(path: str | Path) -> tuple[np.ndarray, dict[str, Any]]:
    """Return (spectrum [freq, time] float32, metadata dict)."""
    fits = _import_fits()
    with fits.open(path, memmap=False) as hdul:
        data = hdul[0].data
        if data is None:
            raise ValueError(f"No primary HDU image data in {path}")
        spectrum = np.squeeze(np.asarray(data, dtype=np.float32))
        if spectrum.ndim != 2:
            raise ValueError(
                f"Expected a 2D spectrum in {path}, got shape {spectrum.shape}"
            )
        metadata = _extract_metadata(path, hdul)
    return spectrum, metadata


# ─── Spectrum processing ───────────────────────────────────────────────────────

def clean_invalid_values(spectrum: np.ndarray) -> np.ndarray:
    data = np.asarray(spectrum, dtype=np.float32)
    finite_mask = np.isfinite(data)
    if not finite_mask.any():
        return np.zeros_like(data, dtype=np.float32)
    replacement = np.median(data[finite_mask]).astype(np.float32)
    return np.where(finite_mask, data, replacement).astype(np.float32)


def plotutil_median_db(spectrum: np.ndarray) -> np.ndarray:
    data = np.asarray(spectrum, dtype=np.float32)
    baseline = np.median(data, axis=1, keepdims=True)
    centered = (data - baseline).astype(np.float32)
    return (centered * np.float32(PLOTUTIL_DB_SCALE)).astype(np.float32)


def db_window_normalize(
    spectrum: np.ndarray,
    vmin: float = -1.0,
    vmax: float = 8.0,
) -> np.ndarray:
    data = np.asarray(spectrum, dtype=np.float32)
    span = float(vmax) - float(vmin)
    if span <= 0:
        raise ValueError(f"db_window needs vmax > vmin, got [{vmin}, {vmax}]")
    return np.clip((data - float(vmin)) / span, 0.0, 1.0).astype(np.float32)


def _linear_resample_weights(
    old_size: int, new_size: int
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    if new_size == 1 or old_size == 1:
        positions = np.zeros(new_size, dtype=np.float64)
    else:
        positions = np.arange(new_size, dtype=np.float64) * (old_size - 1) / (new_size - 1)
    lower = np.floor(positions).astype(np.intp)
    np.clip(lower, 0, old_size - 1, out=lower)
    upper = np.minimum(lower + 1, old_size - 1)
    frac = (positions - lower).astype(np.float32)
    return lower, upper, frac


def _resize_axis(data: np.ndarray, new_size: int, axis: int) -> np.ndarray:
    old_size = data.shape[axis]
    if old_size == new_size:
        return data.astype(np.float32, copy=False)
    lower, upper, frac = _linear_resample_weights(old_size, new_size)
    if axis == 1:
        frac_row = frac[np.newaxis, :]
        return (data[:, lower] * (1.0 - frac_row) + data[:, upper] * frac_row).astype(np.float32)
    if axis == 0:
        frac_col = frac[:, np.newaxis]
        return (data[lower, :] * (1.0 - frac_col) + data[upper, :] * frac_col).astype(np.float32)
    raise ValueError(f"Only 2D arrays supported, got axis={axis}")


def resize_spectrum(spectrum: np.ndarray, target_shape: tuple[int, int] = (224, 224)) -> np.ndarray:
    data = np.asarray(spectrum, dtype=np.float32)
    if data.ndim != 2:
        raise ValueError(f"Expected 2D spectrum, got shape {data.shape}")
    target_freq, target_time = int(target_shape[0]), int(target_shape[1])
    data = _resize_axis(data, target_time, axis=1)
    data = _resize_axis(data, target_freq, axis=0)
    return data.astype(np.float32)


def preprocess_array(spectrum: np.ndarray, config: dict[str, Any]) -> np.ndarray:
    """Full pipeline: clean → background → normalize → resize → [1, H, W]."""
    prep = config["preprocessing"]
    target_shape = tuple(config["data"]["target_shape"])
    data = clean_invalid_values(spectrum)
    data = plotutil_median_db(data)
    data = db_window_normalize(
        data,
        vmin=float(prep.get("db_vmin", PLOTUTIL_DISPLAY_LIMITS[0])),
        vmax=float(prep.get("db_vmax", PLOTUTIL_DISPLAY_LIMITS[1])),
    )
    data = resize_spectrum(data, target_shape=target_shape)
    return data[np.newaxis, :, :].astype(np.float32)


def preprocess_file(
    file_path: str | Path,
    config: dict[str, Any],
) -> tuple[np.ndarray, dict[str, Any]]:
    """Read a FITS file and return (tensor [1,H,W], metadata dict)."""
    spectrum, metadata = read_fits_spectrum(file_path)
    tensor = preprocess_array(spectrum, config)
    return tensor, metadata


def preprocess_bytes(
    content: bytes,
    filename: str,
    config: dict[str, Any],
) -> tuple[np.ndarray, dict[str, Any]]:
    """Preprocess raw FITS bytes preserving the real filename.

    The model is metadata-conditioned: date and station are parsed from the
    e-CALLISTO filename ``STATION_YYYYMMDD_HHMMSS_NN.fit.gz``.  Writing the
    bytes under the real filename (not a random tmp name) keeps the metadata
    features identical to scoring the file directly from the archive.
    """
    safe = Path(filename).name or "remote.fit.gz"
    tmpdir = Path(tempfile.mkdtemp(prefix="swd_ml_"))
    try:
        path = tmpdir / safe
        path.write_bytes(content)
        return preprocess_file(path, config)
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
