"""Type II shock-parameter estimation (Path A) — ported from the desktop app.

Replicates ``e-Callisto_FITS_Analyzer/src/UI/dialogs/analyze_dialog.py`` and the
max-intensity seed extraction in ``src/UI/main_window.py`` so the web analyzer produces
numerically identical shock speed / height:

    burst isolation (polygon mask) -> per-column argmax (maximum-intensity plot)
    -> auto-clean weak columns -> power-law fit f(t)=a*t^(-b) -> Newkirk shock params.

Pure numpy + scipy.optimize; no Qt / sklearn (R^2 and RMSE are computed directly).
"""

from __future__ import annotations

from typing import Any, Sequence

import numpy as np
from matplotlib.path import Path as MplPath
from scipy.optimize import curve_fit

# Frozen constants — must match the desktop app exactly (do not "clean up").
_SHOCK_SPEED_CONST = 13853221.38  # Newkirk + plasma-freq + Rsun unit bundle (km/s)
_NEWKIRK_DENOM = 3.385            # denom = fold * 3.385
_NEWKIRK_RP_COEFF = 4.32          # R_p = 4.32*ln(10)/ln(f^2/denom)
_NEWKIRK_DRP_COEFF = 8.64         # dRp/df numerator coefficient (= 2 * 4.32)
_AUTO_CLEAN_PERCENTILE = 10
_AUTO_CLEAN_FACTOR = 0.15
_START_FREQ_PERCENTILE = 90
_FIT_SAMPLE_COUNT = 400


# ── Maximum-intensity extraction (burst isolation + argmax + auto-clean) ──────


def _burst_mask(
    time_axis: np.ndarray,
    freq_axis: np.ndarray,
    polygon: Sequence[Sequence[float]],
) -> np.ndarray:
    """Boolean (n_freq, n_time) mask of cells inside ``polygon`` (data coords)."""
    verts = np.asarray(polygon, dtype=float)
    if verts.ndim != 2 or verts.shape[0] < 3 or verts.shape[1] != 2:
        raise ValueError("Burst polygon needs at least 3 [time, freq] vertices.")
    tt, ff = np.meshgrid(
        np.asarray(time_axis, dtype=float),
        np.asarray(freq_axis, dtype=float),
    )  # both (n_freq, n_time)
    coords = np.column_stack([tt.ravel(), ff.ravel()])
    inside = MplPath(verts, closed=True).contains_points(coords)
    return inside.reshape(tt.shape)


def _auto_filter_isolated_maxima(
    time_channels: np.ndarray,
    time_seconds: np.ndarray,
    max_freqs: np.ndarray,
    source_data: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, int]:
    """Drop time columns whose peak intensity is < 15% of the 10th-percentile peak.

    Mirrors ``main_window._auto_filter_isolated_maxima``; operates on the per-column
    peak of ``source_data`` and applies the surviving column selection to all vectors.
    """
    vals = np.nanmax(np.asarray(source_data, dtype=float), axis=0)
    finite = np.isfinite(vals)
    positive = vals[finite & (vals > 0)]

    if positive.size > 0:
        base = float(np.nanpercentile(positive, _AUTO_CLEAN_PERCENTILE))
        threshold = max(1e-12, base * _AUTO_CLEAN_FACTOR)
        valid = finite & (vals > threshold)
        if int(np.count_nonzero(valid)) < 3:
            valid = finite & (vals > 0)
    else:
        valid = finite & (vals > 0)

    if int(np.count_nonzero(valid)) < 3:
        return time_channels, time_seconds, max_freqs, 0

    removed = int(time_channels.size - int(np.count_nonzero(valid)))
    return time_channels[valid], time_seconds[valid], max_freqs[valid], max(0, removed)


def extract_max_intensity(
    arr: np.ndarray,
    time_axis: np.ndarray,
    freq_axis: np.ndarray,
    polygon: Sequence[Sequence[float]] | None = None,
    auto_clean: bool = True,
) -> dict[str, Any]:
    """Maximum-intensity frequency per time column of the (optionally isolated) burst.

    ``arr`` is the processed spectrogram (n_freq, n_time); ``polygon`` (data coords:
    [time_seconds, freq_mhz] vertices) isolates the burst by zeroing everything outside
    before the per-column ``argmax`` — matching the desktop's lasso isolation. Returns
    ``time_channels`` (column indices), ``time_seconds`` and ``freqs`` (MHz), plus the
    auto-clean bookkeeping.
    """
    data = np.asarray(arr, dtype=float)
    if data.ndim != 2 or data.shape[1] == 0:
        raise ValueError("Spectrogram must be a 2D array with at least one column.")
    freqs = np.asarray(freq_axis, dtype=float).reshape(-1)
    if freqs.shape[0] != data.shape[0]:
        raise ValueError("freq_axis length must match the number of spectrogram rows.")
    n_time = int(data.shape[1])
    time_channels = np.arange(n_time, dtype=float)
    time_seconds = np.asarray(time_axis, dtype=float).reshape(-1)
    if time_seconds.shape[0] != n_time:
        time_seconds = time_channels.copy()

    isolated = polygon is not None
    if isolated:
        mask = _burst_mask(time_seconds, freqs, polygon)
        data = np.where(mask, data, 0.0)

    finite = np.isfinite(data)
    valid_cols = np.any(finite, axis=0)
    if not np.any(valid_cols):
        raise ValueError("No finite data columns found in the selected region.")
    peak_source = np.where(finite, data, -np.inf)
    peak_indices = np.argmax(peak_source, axis=0)
    max_freqs = freqs[peak_indices]

    if not np.all(valid_cols):
        time_channels = time_channels[valid_cols]
        time_seconds = time_seconds[valid_cols]
        max_freqs = max_freqs[valid_cols]

    auto_removed = 0
    if isolated and auto_clean:
        time_channels, time_seconds, max_freqs, auto_removed = _auto_filter_isolated_maxima(
            time_channels, time_seconds, max_freqs, data
        )

    return {
        "time_channels": time_channels.astype(float).tolist(),
        "time_seconds": time_seconds.astype(float).tolist(),
        "freqs": max_freqs.astype(float).tolist(),
        "auto_outlier_cleaned": bool(auto_removed > 0),
        "auto_removed_count": int(auto_removed),
    }


# ── Power-law fit  f(t) = a * t^(-b) ─────────────────────────────────────────


def _model(x, a, b):
    return a * x ** (-b)


def _drift_rate(x, a, b):
    return -a * b * x ** (-b - 1)


def _fit_mask(time_values: np.ndarray, freq_values: np.ndarray) -> np.ndarray:
    x = np.asarray(time_values, dtype=float).reshape(-1)
    y = np.asarray(freq_values, dtype=float).reshape(-1)
    return np.isfinite(x) & np.isfinite(y) & (x > 0) & (y > 0)


def _initial_guess(time_values: np.ndarray, freq_values: np.ndarray) -> tuple[float, float]:
    x = np.asarray(time_values, dtype=float).reshape(-1)
    y = np.asarray(freq_values, dtype=float).reshape(-1)
    mask = np.isfinite(x) & np.isfinite(y) & (x > 0) & (y > 0)
    if np.count_nonzero(mask) >= 2:
        try:
            slope, intercept = np.polyfit(np.log(x[mask]), np.log(y[mask]), 1)
            a0 = float(np.exp(intercept))
            b0 = float(max(1e-9, -slope))
            if np.isfinite(a0) and a0 > 0 and np.isfinite(b0):
                return a0, b0
        except Exception:
            pass
    positive_freqs = y[np.isfinite(y) & (y > 0)]
    if positive_freqs.size:
        return float(np.nanmax(positive_freqs)), 0.5
    return 1.0, 0.5


def power_law_fit(time_s: Sequence[float], freq_mhz: Sequence[float]) -> dict[str, Any]:
    """Fit ``f = a * t^(-b)`` with scipy.optimize.curve_fit. Returns a/b/std_errs/r2/rmse."""
    t = np.asarray(time_s, dtype=float).reshape(-1)
    f = np.asarray(freq_mhz, dtype=float).reshape(-1)
    mask = _fit_mask(t, f)
    if int(np.count_nonzero(mask)) < 2:
        raise ValueError(
            "Power-law fitting requires at least two points with time > 0 s and frequency > 0 MHz."
        )
    ft, ff = t[mask], f[mask]

    params, cov = curve_fit(
        _model, ft, ff,
        p0=_initial_guess(ft, ff),
        bounds=([1e-12, 1e-9], [np.inf, np.inf]),
        maxfev=10000,
    )
    a, b = float(params[0]), float(params[1])
    with np.errstate(invalid="ignore"):
        std_errs = np.sqrt(np.diag(cov))

    predicted = _model(ft, a, b)
    residuals = ff - predicted
    ss_res = float(np.sum(residuals ** 2))
    ss_tot = float(np.sum((ff - np.mean(ff)) ** 2))
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0
    rmse = float(np.sqrt(np.mean(residuals ** 2)))

    return {
        "a": a,
        "b": abs(b),
        "std_errs": [float(std_errs[0]), float(std_errs[1])],
        "r2": float(r2),
        "rmse": float(rmse),
        "point_count": int(ft.size),
    }


# ── Newkirk shock parameters (speed & height) ────────────────────────────────


def compute_shock_parameters(
    fit: dict[str, Any],
    time_s: Sequence[float],
    freq_mhz: Sequence[float],
    fold: int,
    harmonic: bool,
) -> dict[str, Any]:
    """Shock speed & height from the fitted drift + Newkirk density model.

    Faithful port of ``analyze_dialog._update_shock_parameters`` (and the drift/error
    bookkeeping from ``plot_fit``): shock parameters are evaluated over the fit sampled at
    ``linspace(t.min, t.max, 400)``, while the reported average frequency uses the
    maximum-intensity points. Returns ``shock_summary`` (all desktop fields) plus
    ``curves`` and ``fit_line`` arrays for plotting.
    """
    n = max(1, min(4, int(fold)))
    denom = n * _NEWKIRK_DENOM
    a = float(fit["a"])
    b = abs(float(fit["b"]))
    std_errs = np.asarray(fit.get("std_errs") or [np.nan, np.nan], dtype=float)

    t = np.asarray(time_s, dtype=float).reshape(-1)
    f = np.asarray(freq_mhz, dtype=float).reshape(-1)
    mask = _fit_mask(t, f)
    if int(np.count_nonzero(mask)) < 2:
        raise ValueError("Not enough valid points to compute shock parameters.")
    fit_time, fit_freq = t[mask], f[mask]

    # Fit curve sampled between the first and last valid points.
    time_fit = np.linspace(fit_time.min(), fit_time.max(), _FIT_SAMPLE_COUNT)
    freq_fit = _model(time_fit, a, b)

    # Drift + error propagation on the fit-sampled curve (shock_calc_* in the desktop).
    predicted = _model(fit_time, a, b)
    observed_drift_vals = _drift_rate(fit_time, a, b)
    freq_err = float(np.std(fit_freq - predicted))
    b_err_denom = max(abs(b), 1e-9)
    rel_err = np.sqrt((std_errs[0] / a) ** 2 + (std_errs[1] / b_err_denom) ** 2)

    shock_calc_drift_vals = _drift_rate(time_fit, a, b)
    shock_calc_drift_errs = np.abs(shock_calc_drift_vals) * rel_err

    max_intensity_freq_values = f[np.isfinite(f) & (f > 0.0)]

    harmonic_number = 2.0 if harmonic else 1.0
    shock_freq_values = freq_fit / harmonic_number
    shock_drift_vals = shock_calc_drift_vals / harmonic_number
    shock_drift_errs = shock_calc_drift_errs / harmonic_number
    shock_freq_err = freq_err / harmonic_number

    with np.errstate(divide="ignore", invalid="ignore"):
        g = np.log(shock_freq_values ** 2 / denom)
        shock_speed = (_SHOCK_SPEED_CONST * np.abs(shock_drift_vals)) / (shock_freq_values * g ** 2)
        R_p = _NEWKIRK_RP_COEFF * np.log(10) / g

    avg_freq_values = (
        max_intensity_freq_values / harmonic_number
        if max_intensity_freq_values.size else shock_freq_values
    )

    start_freq = float(np.percentile(shock_freq_values, _START_FREQ_PERCENTILE))
    idx = int(np.abs(shock_freq_values - start_freq).argmin())
    f0 = float(shock_freq_values[idx])
    drift_err0 = float(shock_drift_errs[idx])
    start_shock_speed = float(shock_speed[idx])
    start_height = float(R_p[idx])

    with np.errstate(divide="ignore", invalid="ignore"):
        g0 = np.log(f0 ** 2 / denom)
        shock_speed_err = (_SHOCK_SPEED_CONST * drift_err0) / (f0 * g0 ** 2)
        dRp_df = _NEWKIRK_DRP_COEFF * np.log(10) / (f0 * g0 ** 2)
        Rp_err = float(np.abs(dRp_df * shock_freq_err))

    def _sem(x):
        x = np.asarray(x, dtype=float)
        return float(np.std(x) / np.sqrt(len(x))) if len(x) else 0.0

    summary = {
        "avg_freq_mhz": float(np.mean(avg_freq_values)),
        "avg_freq_err_mhz": _sem(avg_freq_values),
        "avg_drift_mhz_s": float(np.mean(shock_drift_vals)),
        "avg_drift_err_mhz_s": _sem(shock_drift_vals),
        "start_freq_mhz": start_freq,
        "start_freq_err_mhz": float(shock_freq_err),
        "initial_shock_speed_km_s": start_shock_speed,
        "initial_shock_speed_err_km_s": float(shock_speed_err),
        "initial_shock_height_rs": start_height,
        "initial_shock_height_err_rs": Rp_err,
        "avg_shock_speed_km_s": float(np.mean(shock_speed)),
        "avg_shock_speed_err_km_s": _sem(shock_speed),
        "avg_shock_height_rs": float(np.mean(R_p)),
        "avg_shock_height_err_rs": _sem(R_p),
        "fold": int(n),
        "fundamental": bool(not harmonic),
        "harmonic": bool(harmonic),
        "harmonic_number": int(harmonic_number),
        "observed_avg_freq_mhz": (
            float(np.mean(max_intensity_freq_values))
            if max_intensity_freq_values.size else float(np.mean(fit_freq))
        ),
        "observed_avg_drift_mhz_s": float(np.mean(observed_drift_vals)),
        "observed_start_freq_mhz": float(np.percentile(fit_freq, _START_FREQ_PERCENTILE)),
    }

    curves = {
        "shock_freq_mhz": shock_freq_values.astype(float).tolist(),
        "shock_speed_km_s": shock_speed.astype(float).tolist(),
        "shock_height_rs": R_p.astype(float).tolist(),
    }
    fit_line = {
        "time_s": time_fit.astype(float).tolist(),
        "freq_mhz": freq_fit.astype(float).tolist(),
    }
    return {"shock_summary": summary, "curves": curves, "fit_line": fit_line}
