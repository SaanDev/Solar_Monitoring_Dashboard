"""Processing for the interactive e-CALLISTO Analyzer.

Ports the few numpy algorithms the standalone desktop analyzer uses (robust
per-channel background subtraction, digits->dB conversion, percentile display
limits) and reuses the dashboard's existing helpers (``digit_to_voltage``,
``percentile_clip``). Pure functions — no I/O — so they stay unit-testable.
"""
from __future__ import annotations

import numpy as np
from matplotlib.colors import Colormap, LinearSegmentedColormap
from matplotlib import colormaps as mpl_colormaps

from app.processing.rfi_cleaning import percentile_clip

# CALLISTO log-detector calibration (mirrors background_subtraction.py constants):
# 255 digits == 2500 mV, ~25.4 mV per dB.
DEFAULT_DB_SCALE = 2500.0 / 255.0 / 25.4

BACKGROUND_METHODS = ("mean", "median", "robust")
INTENSITY_UNITS = ("digits", "db")
TIME_UNITS = ("seconds", "utc")

# Colormaps offered in the UI. "custom" is the desktop app's blue->red->yellow ramp.
COLORMAPS = (
    "custom",
    "viridis",
    "plasma",
    "inferno",
    "magma",
    "cividis",
    "turbo",
    "RdYlBu",
    "jet",
    "cubehelix",
    "bone_r",
)
_CUSTOM_CMAP = LinearSegmentedColormap.from_list(
    "callisto_custom", ["#0000ff", "#ff0000", "#ffff00"]
)


def resolve_cmap(name: str) -> Colormap:
    """Return a matplotlib Colormap for an allow-listed name (raises otherwise)."""
    if name not in COLORMAPS:
        raise ValueError(f"Unsupported colormap: {name!r}")
    if name == "custom":
        return _CUSTOM_CMAP
    return mpl_colormaps[name]


def subtract_background_rows(data: np.ndarray, method: str = "median") -> np.ndarray:
    """Subtract a per-frequency-channel baseline (the quiescent background per row).

    ``method``: "mean", "median", or "robust" (per-row 25th percentile). Ported
    and simplified from the desktop analyzer's noise_reduction.subtract_background_rows.
    """
    arr = np.asarray(data, dtype=np.float32)
    if arr.ndim != 2:
        raise ValueError(f"Expected 2D data, got ndim={arr.ndim}.")
    mode = (method or "median").strip().lower()
    if mode == "mean":
        baseline = np.nanmean(arr, axis=1, keepdims=True)
    elif mode == "median":
        baseline = np.nanmedian(arr, axis=1, keepdims=True)
    elif mode in {"robust", "percentile", "p25"}:
        baseline = np.nanpercentile(arr, 25.0, axis=1, keepdims=True)
    else:
        raise ValueError(f"Unsupported background method: {method!r}")
    return (arr - baseline).astype(np.float32, copy=False)


def convert_digits_to_db(
    data: np.ndarray, cold_digits: float = 0.0, db_scale: float = DEFAULT_DB_SCALE
) -> np.ndarray:
    """Convert raw e-CALLISTO digits to dB above a cold-load reference."""
    arr = np.asarray(data, dtype=np.float32)
    return (arr - float(cold_digits)) * float(db_scale)


def percentile_data_limits(
    data: np.ndarray, lower: float = 5.0, upper: float = 98.0
) -> tuple[float, float]:
    """Robust (vmin, vmax) from data percentiles; falls back to (0, 1) if empty."""
    finite = np.asarray(data, dtype=float)
    finite = finite[np.isfinite(finite)]
    if finite.size == 0:
        return 0.0, 1.0
    lo, hi = sorted((float(np.clip(lower, 0, 100)), float(np.clip(upper, 0, 100))))
    vmin = float(np.percentile(finite, lo))
    vmax = float(np.percentile(finite, hi))
    if vmax <= vmin:
        vmax = vmin + 1e-6
    return vmin, vmax


def default_limits(data: np.ndarray, intensity_unit: str) -> tuple[float, float]:
    """Sensible initial display range for the given intensity unit."""
    if intensity_unit == "db":
        return -1.0, 8.0  # e-CALLISTO dB-above-background display range
    return percentile_data_limits(data, 5.0, 98.0)


def process_spectrum(
    data: np.ndarray,
    *,
    intensity_unit: str = "db",
    method: str = "median",
    rfi_enabled: bool = False,
    rfi_low: float = 1.0,
    rfi_high: float = 99.0,
) -> tuple[np.ndarray, str]:
    """Apply the analyzer pipeline. Returns (processed array, colorbar label).

    Steps: optional RFI percentile clip -> (optional digits->dB) -> per-channel
    background subtraction by ``method``.
    """
    if intensity_unit not in INTENSITY_UNITS:
        raise ValueError(f"Unsupported intensity unit: {intensity_unit!r}")

    arr = np.asarray(data, dtype=np.float32)
    if rfi_enabled:
        arr = percentile_clip(arr, low=rfi_low, high=rfi_high)

    if intensity_unit == "db":
        arr = convert_digits_to_db(arr)
        label = "dB above background"
    else:
        label = "counts above background"

    return subtract_background_rows(arr, method=method), label
