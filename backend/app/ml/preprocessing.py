"""Read e-CALLISTO FITS spectra and build CCM v2.0's image inputs.

Ported from the CALLISTO Trainer (``core/fits_reader.py``, ``core/preprocess.py``,
``core/crops.py`` and ``core/coords.py``). The model only means anything on input
prepared exactly the way its training samples were, so every numeric step here
mirrors its original; change one and the model still answers, confidently and
wrongly.

Pipeline per file:
  1. Read the 2D [frequency, time] spectrum, its physical axes and the station's
     flagged RFI channels. The axes come from the ``AXES`` bintable when the file
     has one and are synthesized from the header otherwise — the header's
     CRVAL2/CDELT2 are placeholders on this archive, but training synthesized
     them the same way, so the model's physics features expect it.
  2. Normalize the **whole** file: NaN/Inf -> finite median, per-channel median
     background in Plotutil dB, then the [-1, 8] dB window mapped to [0, 1].
  3. The same with each channel's *quiet* background (its 10th percentile), so a
     continuum lasting most of the file stays visible.
  4. Per candidate region, three 224x224 views: the exact crop, a wide context
     strip (full band, extended in time) and that strip of the quiet array.

Background subtraction must run over the whole file's time axis before any crop
is taken: cropped first, a burst that fills its crop becomes its own baseline
and is erased.

All numeric steps are pure NumPy — identical results on every machine.
"""
from __future__ import annotations

import shutil
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator

import numpy as np

# ── Raw digit -> dB conversion (Plotutil Digit2Voltage / 25.4) ────────────────

PLOTUTIL_DB_SCALE = 2500.0 / 255.0 / 25.4
PLOTUTIL_DISPLAY_LIMITS = (-1.0, 8.0)
_PLOTUTIL_METHODS = {"plotutil_median_db", "plotutil", "plotutil_median", "ecallisto_db"}

# Each channel's background for the quiet-background view: this percentile of
# its samples over the file, i.e. its quietest tenth.
QUIET_PERCENTILE = 10.0

VIEW_CROP = "crop"
VIEW_CONTEXT = "context"
VIEW_QUIET_CONTEXT = "quiet_context"
VIEWS = (VIEW_CROP, VIEW_CONTEXT, VIEW_QUIET_CONTEXT)


# ─── Physical axes ────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class SpectrumAxes:
    """Physical axes of one dynamic spectrum, in array row/column order.

    ``time_s[j]`` is column ``j``'s offset in seconds from the first sample and
    ``freq_mhz[i]`` row ``i``'s frequency — normally *descending*, since row 0 is
    the first FITS row. ``source`` is ``"axes_table"`` when the frequencies are
    real, ``"header"`` when synthesized from the unreliable header keywords.
    """

    time_s: np.ndarray
    freq_mhz: np.ndarray
    source: str = "none"

    @property
    def n_time(self) -> int:
        return int(self.time_s.size)

    @property
    def n_freq(self) -> int:
        return int(self.freq_mhz.size)


def box_to_physical(
    axes: SpectrumAxes, row0: int, row1: int, col0: int, col1: int
) -> dict[str, float]:
    """A half-open pixel box's bounds in MHz and seconds (``lo``/``hi`` ordered)."""

    def at(values: np.ndarray, index: int) -> float:
        if values.size == 0:
            return float("nan")
        return float(np.interp(index, np.arange(values.size, dtype=np.float64), values))

    freq_a = at(axes.freq_mhz, max(0, int(row0)))
    freq_b = at(axes.freq_mhz, max(0, int(row1) - 1))
    time_a = at(axes.time_s, max(0, int(col0)))
    time_b = at(axes.time_s, max(0, int(col1) - 1))
    return {
        "freq_lo_mhz": min(freq_a, freq_b),
        "freq_hi_mhz": max(freq_a, freq_b),
        "t_start_s": min(time_a, time_b),
        "t_end_s": max(time_a, time_b),
    }


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


def read_rfi_channels(hdul: Any) -> np.ndarray | None:
    """The station's flagged interference frequencies (MHz), from ``RFI_FREQ``."""
    names = {str(getattr(hdu, "name", "") or "").strip().upper() for hdu in hdul}
    if "RFI_FREQ" not in names:
        return None
    try:
        table = hdul["RFI_FREQ"].data
        if table is None or len(table.columns.names) == 0:
            return None
        values = np.asarray(table[table.columns.names[0]], dtype=np.float64).ravel()
    except Exception:
        return None
    values = values[np.isfinite(values)]
    return values if values.size else None


def _cadence_from_header(header: Any) -> float | None:
    try:
        cadence = float(header.get("CDELT1"))
    except (TypeError, ValueError):
        return None
    return cadence if cadence > 0 else None


def synthesize_axes(header: Any, n_freq: int, n_time: int) -> tuple[np.ndarray, np.ndarray]:
    """Approximate axes from the header, for files without an AXES table.

    CRVAL2/CDELT2 are placeholders on this archive (usually a channel index), so
    the frequencies are not real MHz — but this is exactly how training built
    them, and the model's physics features are scaled accordingly.
    """
    cadence = _cadence_from_header(header) or 1.0
    time_s = np.arange(int(n_time), dtype=np.float64) * cadence
    try:
        crval = float(header.get("CRVAL2"))
        cdelt = float(header.get("CDELT2"))
    except (TypeError, ValueError):
        crval, cdelt = float(n_freq), -1.0
    freq_mhz = crval + np.arange(int(n_freq), dtype=np.float64) * cdelt
    return time_s, freq_mhz


def _extract_metadata(path: str | Path, hdul: Any) -> dict[str, Any]:
    fallback = parse_filename_fallback(path)
    header = hdul[0].header
    data = hdul[0].data
    shape = tuple(data.shape) if data is not None else ()
    n_freq = int(shape[-2]) if len(shape) >= 2 else 0
    n_time = int(shape[-1]) if len(shape) >= 2 else 0

    time_s, freq_mhz = read_axes(hdul, n_freq=n_freq, n_time=n_time)
    source = "axes_table"
    if time_s is None or freq_mhz is None:
        time_s, freq_mhz = synthesize_axes(header, n_freq, n_time)
        source = "header"

    header_date = _format_date_token(_clean_header_string(header.get("DATE-OBS")))
    header_time = _format_time_token(_clean_header_string(header.get("TIME-OBS")))
    return {
        "station": _clean_header_string(header.get("INSTRUME")) or fallback["station"],
        "date": header_date or fallback["date"],
        "start_time": header_time or fallback["start_time"],
        "n_freq": n_freq,
        "n_time": n_time,
        "axes": SpectrumAxes(time_s=time_s, freq_mhz=freq_mhz, source=source),
        "rfi_channels_mhz": read_rfi_channels(hdul),
    }


def read_fits_spectrum(path: str | Path) -> tuple[np.ndarray, dict[str, Any]]:
    """Return (spectrum [freq, time] float32, metadata incl. ``axes``)."""
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
    """Raw FITS bytes -> (spectrum [freq, time], metadata incl. ``axes``)."""
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


def quiet_normalized_spectrum(
    spectrum: np.ndarray, prep: dict[str, Any], percentile: float = QUIET_PERCENTILE
) -> np.ndarray:
    """The whole file with each channel's background taken from its quiet part.

    Identical to :func:`normalize_full_spectrum` except for the baseline — the
    ``percentile``-th sample of each channel instead of its median — so emission
    lasting most of the recording (a Type IV continuum) stays above background.
    """
    vmin, vmax = _check_preprocessing(prep)
    data = clean_invalid_values(spectrum)
    baseline = np.percentile(data, float(percentile), axis=1, keepdims=True).astype(np.float32)
    data = (data - baseline).astype(np.float32)
    data = (data * np.float32(PLOTUTIL_DB_SCALE)).astype(np.float32)
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


def _max_pool_axis(data: np.ndarray, target: int, axis: int) -> np.ndarray:
    """Block-max along ``axis`` down to no fewer than ``target`` samples."""
    size = data.shape[axis]
    factor = size // max(1, int(target))
    if factor < 2:
        return data
    blocks = int(np.ceil(size / factor))
    padding = blocks * factor - size
    if padding:
        widths = [(0, 0), (0, 0)]
        widths[axis] = (0, padding)
        data = np.pad(data, widths, mode="edge")
    if axis == 1:
        return data.reshape(data.shape[0], blocks, factor).max(axis=2)
    return data.reshape(blocks, factor, data.shape[1]).max(axis=1)


def resize_keeping_peaks(patch: np.ndarray, target_shape: tuple[int, int]) -> np.ndarray:
    """Resize with a max-pool first, so one-sample interference spikes survive."""
    data = np.asarray(patch, dtype=np.float32)
    data = _max_pool_axis(data, int(target_shape[1]), axis=1)
    data = _max_pool_axis(data, int(target_shape[0]), axis=0)
    return resize_spectrum(data, target_shape=target_shape)


# ─── Region views ─────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class PixelBox:
    """A half-open box in spectrum pixels: rows ``[row0, row1)``, cols ``[col0, col1)``."""

    row0: int
    row1: int
    col0: int
    col1: int

    def __post_init__(self) -> None:
        if self.row1 <= self.row0 or self.col1 <= self.col0:
            raise ValueError(
                f"PixelBox must have positive extent, got rows [{self.row0}, {self.row1}) "
                f"cols [{self.col0}, {self.col1})"
            )

    @property
    def n_rows(self) -> int:
        return self.row1 - self.row0

    @property
    def n_cols(self) -> int:
        return self.col1 - self.col0


@dataclass(frozen=True)
class CropConfig:
    """Crop geometry, from the checkpoint's ``crops`` section.

    CCM v2.0 was trained with zero margin and no size floor, so a crop is exactly
    the region; the fields exist so a checkpoint trained otherwise still crops
    the way it was trained.
    """

    context_margin: float = 0.0
    min_rows: int = 1
    min_cols: int = 1
    target_shape: tuple[int, int] = (224, 224)
    # The context view extends a region by its own width on each side, and by at
    # least this many samples (about a minute at the usual 0.25 s cadence).
    context_min_pad_cols: int = 240

    @classmethod
    def from_config(cls, config: dict[str, Any]) -> "CropConfig":
        crops = config.get("crops", {}) or {}
        target = crops.get("target_shape") or config["data"]["target_shape"]
        return cls(
            context_margin=float(crops.get("context_margin", 0.0)),
            min_rows=int(crops.get("min_rows", 1)),
            min_cols=int(crops.get("min_cols", 1)),
            target_shape=(int(target[0]), int(target[1])),
            context_min_pad_cols=int(crops.get("context_min_pad_cols", 240)),
        )


def _grow_to_minimum(low: int, high: int, minimum: int, limit: int) -> tuple[int, int]:
    target = min(int(minimum), limit)
    deficit = target - (high - low)
    if deficit <= 0:
        return low, high
    return low - deficit // 2, high + (deficit - deficit // 2)


def _clamp_span(low: int, high: int, limit: int) -> tuple[int, int]:
    """Shift then clip ``[low, high)`` into ``[0, limit)``, keeping its width if possible."""
    width = min(high - low, limit)
    if low < 0:
        low, high = 0, width
    if high > limit:
        high, low = limit, limit - width
    return max(0, low), min(limit, max(high, low + 1))


def expand_box(box: PixelBox, shape: tuple[int, ...], crop: CropConfig) -> PixelBox:
    """Grow a box by the margin and up to the minimum size, clamped to bounds."""
    n_freq, n_time = int(shape[0]), int(shape[1])
    row_pad = int(round(box.n_rows * crop.context_margin))
    col_pad = int(round(box.n_cols * crop.context_margin))
    row0, row1 = _grow_to_minimum(box.row0 - row_pad, box.row1 + row_pad, crop.min_rows, n_freq)
    col0, col1 = _grow_to_minimum(box.col0 - col_pad, box.col1 + col_pad, crop.min_cols, n_time)
    row0, row1 = _clamp_span(row0, row1, n_freq)
    col0, col1 = _clamp_span(col0, col1, n_time)
    return PixelBox(row0, row1, col0, col1)


def crop_view(normalized: np.ndarray, box: PixelBox, crop: CropConfig) -> np.ndarray:
    """The region itself, resized to the model input as ``[H, W]``."""
    effective = expand_box(box, normalized.shape, crop)
    patch = normalized[effective.row0:effective.row1, effective.col0:effective.col1]
    return resize_spectrum(patch, target_shape=crop.target_shape)


def context_view(normalized: np.ndarray, box: PixelBox, crop: CropConfig) -> np.ndarray:
    """The full band over the region's columns widened each side, as ``[H, W]``.

    Where interference gives itself away: a carrier continues far beyond the box,
    an impulse runs the full height of the band, periodic interference repeats.
    """
    n_freq, n_time = normalized.shape
    pad = max(box.n_cols, int(crop.context_min_pad_cols))
    col0, col1 = _clamp_span(box.col0 - pad, box.col1 + pad, n_time)
    return resize_keeping_peaks(normalized[0:n_freq, col0:col1], crop.target_shape)


def region_views(
    normalized: np.ndarray,
    box: PixelBox,
    crop: CropConfig,
    views: tuple[str, ...],
    quiet: np.ndarray | None = None,
) -> np.ndarray:
    """Stack the model's views of one region into a ``[V, H, W]`` tensor."""
    layers = []
    for view in views:
        if view == VIEW_CROP:
            layers.append(crop_view(normalized, box, crop))
        elif view == VIEW_CONTEXT:
            layers.append(context_view(normalized, box, crop))
        elif view == VIEW_QUIET_CONTEXT:
            if quiet is None:
                raise ValueError("the quiet_context view needs the quiet-background spectrum")
            layers.append(context_view(quiet, box, crop))
        else:
            raise ValueError(f"Unknown view {view!r}; expected one of {VIEWS}")
    return np.stack(layers).astype(np.float32)
