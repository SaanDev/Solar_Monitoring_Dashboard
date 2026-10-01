"""Read e-CALLISTO FITS spectra and build BnB v1.0's whole-file input.

Ported from the CALLISTO Trainer (``core/fits_reader.py``, ``core/preprocess.py``
and ``core/crops.py``). The model only means anything on input prepared exactly
the way its training samples were, so every numeric step here mirrors its
original; change one and the model still answers, confidently and wrongly.

Pipeline per file:
  1. Read the 2D [frequency, time] spectrum and the metadata the model's
     metadata branch takes: station, date and frequency range. The frequency
     range comes from the ``AXES`` bintable when the file has one and from the
     header's CRVAL2/CDELT2 otherwise — placeholders on this archive (usually a
     channel index), but exactly what training read for the same files.
  2. Normalize the **whole** file: NaN/Inf -> finite median, per-channel median
     background in Plotutil dB, then the [-1, 8] dB window mapped to [0, 1].
  3. Resize the whole normalized file to the 224x224 input.

Background subtraction must run over the whole file's time axis: a burst
filling a shorter stretch becomes its own baseline and is erased.

All numeric steps are pure NumPy — identical results on every machine.
"""
from __future__ import annotations

import shutil
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

import numpy as np

# ── Raw digit -> dB conversion (Plotutil Digit2Voltage / 25.4) ────────────────

PLOTUTIL_DB_SCALE = 2500.0 / 255.0 / 25.4
PLOTUTIL_DISPLAY_LIMITS = (-1.0, 8.0)
_PLOTUTIL_METHODS = {"plotutil_median_db", "plotutil", "plotutil_median", "ecallisto_db"}


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
    """``YYYYMMDD`` / ``YYYY-MM-DD`` / ``YYYY/MM/DD`` (as DATE-OBS writes it)."""
    if token is None:
        return None
    token = token.strip()
    if len(token) == 8 and token.isdigit():
        return f"{token[0:4]}-{token[4:6]}-{token[6:8]}"
    if len(token) >= 10 and token[4] in "-/" and token[7] in "-/":
        return token[:10].replace("/", "-")
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


def _axis_table_candidates(hdul: Any) -> list[Any]:
    """Extensions holding TIME and FREQUENCY columns, one named AXES first.

    Located by structure, not by name: much of the archive writes the identical
    table with no EXTNAME at all.
    """
    named, unnamed = [], []
    for hdu in hdul[1:]:
        if not hasattr(hdu, "columns"):
            continue
        try:
            columns = {name.strip().upper() for name in hdu.columns.names}
        except Exception:
            continue
        if not {"TIME", "FREQUENCY"} <= columns:
            continue
        if str(getattr(hdu, "name", "") or "").strip().upper() == "AXES":
            named.append(hdu)
        else:
            unnamed.append(hdu)
    return named + unnamed


def read_axes(
    hdul: Any, n_freq: int | None = None, n_time: int | None = None
) -> tuple[np.ndarray | None, np.ndarray | None]:
    """``(time_seconds, frequency_mhz)`` from the file's axis table, or Nones.

    A table whose lengths disagree with the image is skipped rather than trusted.
    Time is returned as an offset from the first sample, since some writers store
    the absolute second-of-day.
    """
    for hdu in _axis_table_candidates(hdul):
        try:
            table = hdu.data
            if table is None:
                continue
            time_s = np.asarray(table["TIME"], dtype=np.float64).ravel()
            freq_mhz = np.asarray(table["FREQUENCY"], dtype=np.float64).ravel()
        except Exception:
            continue
        if time_s.size == 0 or freq_mhz.size == 0:
            continue
        if not np.isfinite(time_s).all() or not np.isfinite(freq_mhz).all():
            continue
        if n_time is not None and time_s.size != int(n_time):
            continue
        if n_freq is not None and freq_mhz.size != int(n_freq):
            continue
        return time_s - float(time_s[0]), freq_mhz
    return None, None


def header_frequency_bounds(
    header: Any, n_freq: int | None = None
) -> tuple[float | None, float | None]:
    """``(min, max)`` frequency from CRVAL2/CDELT2, as training read them.

    These numbers are wrong for most of this archive (CRVAL2 is usually a channel
    index), but a file without an AXES table was trained on exactly these values,
    so the model expects them.
    """
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

    _, freq_mhz = read_axes(hdul, n_freq=n_freq, n_time=n_time)
    if freq_mhz is not None:
        freq_min: float | None = float(np.min(freq_mhz))
        freq_max: float | None = float(np.max(freq_mhz))
        source = "axes_table"
    else:
        freq_min, freq_max = header_frequency_bounds(header, n_freq=n_freq)
        source = "header" if freq_min is not None else "none"

    header_date = _format_date_token(_clean_header_string(header.get("DATE-OBS")))
    header_time = _format_time_token(_clean_header_string(header.get("TIME-OBS")))
    return {
        "station": _clean_header_string(header.get("INSTRUME")) or fallback["station"],
        "date": header_date or fallback["date"],
        "start_time": header_time or fallback["start_time"],
        "n_freq": n_freq,
        "n_time": n_time,
        "freq_min_mhz": freq_min,
        "freq_max_mhz": freq_max,
        "freq_axis_source": source,
    }


def read_fits_spectrum(path: str | Path) -> tuple[np.ndarray, dict[str, Any]]:
    """Return (spectrum [freq, time] float32, metadata)."""
    fits = _import_fits()
    with fits.open(path, memmap=False) as hdul:
        data = hdul[0].data
        if data is None:
            raise ValueError(f"No primary HDU image data in {path}")
        spectrum = np.squeeze(np.asarray(data, dtype=np.float32))
        if spectrum.ndim != 2:
            raise ValueError(f"Expected a 2D spectrum in {path}, got shape {spectrum.shape}")
        metadata = _extract_metadata(path, hdul)
    return spectrum, metadata


@contextmanager
def _with_real_filename(content: bytes, filename: str) -> Iterator[Path]:
    """Write bytes to a temp dir under their real filename.

    Station, date and time fall back to the e-CALLISTO filename
    ``STATION_YYYYMMDD_HHMMSS_NN.fit.gz`` when the header lacks them, so a random
    temp name would lose them.
    """
    safe = Path(filename).name or "remote.fit.gz"
    tmpdir = Path(tempfile.mkdtemp(prefix="swd_ml_"))
    try:
        path = tmpdir / safe
        path.write_bytes(content)
        yield path
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def read_spectrum_bytes(content: bytes, filename: str) -> tuple[np.ndarray, dict[str, Any]]:
    """Raw FITS bytes -> (spectrum [freq, time], metadata)."""
    with _with_real_filename(content, filename) as path:
        return read_fits_spectrum(path)


# ─── Normalization (whole file) ───────────────────────────────────────────────


def clean_invalid_values(spectrum: np.ndarray) -> np.ndarray:
    data = np.asarray(spectrum, dtype=np.float32)
    finite_mask = np.isfinite(data)
    if not finite_mask.any():
        return np.zeros_like(data, dtype=np.float32)
    replacement = np.median(data[finite_mask]).astype(np.float32)
    return np.where(finite_mask, data, replacement).astype(np.float32)


def plotutil_median_db(spectrum: np.ndarray) -> np.ndarray:
    """Per-channel median over time subtracted, then scaled to Plotutil dB."""
    data = np.asarray(spectrum, dtype=np.float32)
    baseline = np.median(data, axis=1, keepdims=True)
    centered = (data - baseline).astype(np.float32)
    return (centered * np.float32(PLOTUTIL_DB_SCALE)).astype(np.float32)


def db_window_normalize(
    spectrum: np.ndarray, vmin: float = -1.0, vmax: float = 8.0
) -> np.ndarray:
    data = np.asarray(spectrum, dtype=np.float32)
    span = float(vmax) - float(vmin)
    if span <= 0:
        raise ValueError(f"db_window needs vmax > vmin, got [{vmin}, {vmax}]")
    return np.clip((data - float(vmin)) / span, 0.0, 1.0).astype(np.float32)


def _check_preprocessing(prep: dict[str, Any]) -> tuple[float, float]:
    """The dB window, after confirming the checkpoint uses the supported steps."""
    method = str(prep.get("background_method") or "").strip().lower().replace("-", "_")
    if method not in _PLOTUTIL_METHODS:
        raise ValueError(f"unsupported background_method {method!r}")
    normalization = str(prep.get("normalization", "db_window")).lower()
    if normalization != "db_window":
        raise ValueError(f"unsupported normalization {normalization!r}")
    return (
        float(prep.get("db_vmin", PLOTUTIL_DISPLAY_LIMITS[0])),
        float(prep.get("db_vmax", PLOTUTIL_DISPLAY_LIMITS[1])),
    )


def normalize_full_spectrum(spectrum: np.ndarray, prep: dict[str, Any]) -> np.ndarray:
    """clean -> background -> normalize on the **whole** file, without resizing."""
    vmin, vmax = _check_preprocessing(prep)
    data = plotutil_median_db(clean_invalid_values(spectrum))
    return db_window_normalize(data, vmin=vmin, vmax=vmax)


# ─── Resizing ─────────────────────────────────────────────────────────────────


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
    data = _resize_axis(data, int(target_shape[1]), axis=1)
    data = _resize_axis(data, int(target_shape[0]), axis=0)
    return data.astype(np.float32)


def whole_file_tensor(
    normalized: np.ndarray, target_shape: tuple[int, int] = (224, 224)
) -> np.ndarray:
    """The model input for a whole normalized file, as ``[1, H, W]``."""
    return resize_spectrum(normalized, target_shape=target_shape)[np.newaxis, :, :]
