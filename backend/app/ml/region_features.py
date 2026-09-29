"""Features that tell a solar burst from interference, measured per region.

Ported from the CALLISTO Trainer (``core/region_features.py``). Every candidate
region is resized to a 224x224 crop before the network sees it, and that resize
throws away precisely the evidence that separates the commonest false positives
from real bursts: a narrowband carrier that stays bright for the whole file, a
broadband impulse that lights every channel in the same sample, a one-sample-thin
swept signal, periodic interference, a flat gain step, a noisy station. Each
feature below measures one of those directly on the whole-file normalized array,
bounded or log-compressed to order 1.

CCM v2.0's feature input (``region_v2``) is the 8 physics features of
:mod:`app.ml.physics` followed by the 20 :data:`REGION_FEATURES` here — 28
floats, in this fixed order.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import numpy as np

from app.ml.physics import (
    NUM_PHYSICS_FEATURES,
    BurstPhysics,
    cadence_seconds,
    count_bursts,
    physics_to_vector,
)
from app.ml.preprocessing import SpectrumAxes
from app.ml.regions import resolve_threshold

# Fewer bright pixels than this and a region is measured at a relaxed, local
# level instead (and flagged ``faint``), rather than returning all zeros.
MIN_REGION_PIXELS = 5
FAINT_FLOOR = 0.15
FAINT_PERCENTILE = 93.0
# Periodicity is judged over at least this much time around the region.
PERIODICITY_WINDOW_S = 120.0
MIN_PERIOD_S = 1.0

FEATURE_SET_REGION_V2 = "region_v2"

# Order is fixed: it defines the model's feature input.
REGION_FEATURES: tuple[str, ...] = (
    "outside_persistence",   # carriers: the same channels bright outside the region
    "band_fraction",         # impulses and steps cover most of the band
    "simultaneity",          # ... and light it all in the same sample
    "log_onset_spread",      # a drifting burst starts at different times per channel
    "log_thickness_time",    # sweeps and impulses are one or two samples thin
    "log_thickness_freq",    # carriers are one to three channels thin
    "fill_fraction",         # patchy noise fills little of its bounding box
    "log_snr",               # emission well above the file's own noise
    "peakiness",             # a burst peaks; a plateau (gain step) does not
    "periodicity",           # regular repetition, i.e. interference
    "log_period",
    "duration_fraction",     # carriers and steps span much of the recording
    "rfi_flag_fraction",     # channels the station itself flags as RFI
    "burst_count",           # separate bursts: one Type III, or a group (IIIG)
    "log_rows",              # region geometry, which the resize discards
    "log_cols",
    "file_bright_fraction",  # how cluttered the whole recording is
    "file_noise",
    "log_freq_mid",
    "faint",                 # measured at the relaxed local level
)
FEATURE_COUNT = NUM_PHYSICS_FEATURES + len(REGION_FEATURES)


@dataclass
class FileContext:
    """Whole-file statistics shared by every region of one recording.

    Computed once per file so measuring a region costs only a slice of the array.
    """

    normalized: np.ndarray
    level: float
    bright: np.ndarray            # bool [freq, time], normalized >= level
    row_bright: np.ndarray        # bright samples per channel
    col_bright: np.ndarray        # bright channels per sample
    row_cumsum: np.ndarray        # cumulative sum over channels, for band means
    median: float
    noise: float                  # robust sigma of the normalized array
    bright_fraction: float
    cadence_s: float
    freq_mhz: np.ndarray | None
    rfi_rows: np.ndarray | None   # bool [freq], channels in the RFI_FREQ table

    @property
    def n_freq(self) -> int:
        return int(self.normalized.shape[0])

    @property
    def n_time(self) -> int:
        return int(self.normalized.shape[1])

    def band_mean(self, row0: int, row1: int, col0: int, col1: int) -> np.ndarray:
        """Mean over channels ``[row0, row1)`` of each sample in ``[col0, col1)``."""
        top = self.row_cumsum[row1 - 1, col0:col1]
        below = self.row_cumsum[row0 - 1, col0:col1] if row0 > 0 else 0.0
        return (top - below) / float(max(1, row1 - row0))


def _rfi_rows(freq_mhz: np.ndarray | None, rfi_channels: Any) -> np.ndarray | None:
    if freq_mhz is None or rfi_channels is None:
        return None
    flagged = np.atleast_1d(np.asarray(rfi_channels, dtype=float))
    flagged = flagged[np.isfinite(flagged)]
    if flagged.size == 0 or freq_mhz.size == 0:
        return None
    spacing = float(np.median(np.abs(np.diff(freq_mhz)))) if freq_mhz.size > 1 else 1.0
    tolerance = max(0.5 * spacing, 0.05)
    distance = np.abs(freq_mhz[:, None] - flagged[None, :]).min(axis=1)
    return distance <= tolerance


def file_context(
    normalized: np.ndarray,
    axes: SpectrumAxes | None = None,
    rfi_channels: Any = None,
) -> FileContext:
    """Precompute the whole-file statistics for :func:`measure_region`.

    "Bright" uses the region finder's default adaptive threshold — what training
    used, whatever the finder settings a checkpoint records.
    """
    data = np.asarray(normalized, dtype=np.float32)
    if data.ndim != 2:
        raise ValueError(f"Expected a 2D normalized spectrum, got {data.shape}")
    threshold = float(resolve_threshold(data))
    bright = data >= threshold
    median = float(np.median(data))
    noise = float(1.4826 * np.median(np.abs(data - median)))
    freq_mhz = None
    if axes is not None and axes.n_freq == data.shape[0]:
        freq_mhz = np.asarray(axes.freq_mhz, dtype=float)
    return FileContext(
        normalized=data,
        level=threshold,
        bright=bright,
        row_bright=bright.sum(axis=1),
        col_bright=bright.sum(axis=0),
        row_cumsum=np.cumsum(data, axis=0, dtype=np.float32),
        median=median,
        noise=noise,
        bright_fraction=float(bright.mean()),
        cadence_s=cadence_seconds(axes),
        freq_mhz=freq_mhz,
        rfi_rows=_rfi_rows(freq_mhz, rfi_channels),
    )


def _run_thickness(mask: np.ndarray) -> float:
    """Median length of a bright run along axis 1, over the rows that have one."""
    lengths: list[float] = []
    for line in mask:
        count = int(line.sum())
        if not count:
            continue
        starts = int(np.count_nonzero(np.diff(np.concatenate(([0], line.astype(np.int8)))) == 1))
        lengths.append(count / max(1, starts))
    return float(np.median(lengths)) if lengths else 0.0


def _periodicity(series: np.ndarray, cadence_s: float) -> tuple[float, float]:
    """``(score, period_s)`` of the strongest repetition in a time series.

    The period is the most prominent autocorrelation peak; the score is a comb
    contrast — the autocorrelation at L, 2L, 3L minus its value half-way between.
    Regular interference scores near 1; a single burst, a plateau or noise near 0.
    """
    x = np.asarray(series, dtype=np.float64)
    if x.size < 16:
        return 0.0, 0.0
    x = x - float(np.median(x))
    if not np.isfinite(x).all() or float(np.abs(x).max()) < 1e-6:
        return 0.0, 0.0
    spectrum = np.fft.rfft(x, n=2 * x.size)
    autocorr = np.fft.irfft(spectrum * np.conj(spectrum))[: x.size]
    if autocorr[0] <= 0:
        return 0.0, 0.0
    autocorr = autocorr / autocorr[0]

    cadence = cadence_s if cadence_s > 0 else 0.25
    min_lag = max(2, int(round(MIN_PERIOD_S / cadence)))
    max_lag = x.size // 3
    if max_lag <= min_lag + 2:
        return 0.0, 0.0

    from scipy.signal import find_peaks

    segment = autocorr[min_lag:max_lag]
    peaks, properties = find_peaks(segment, prominence=0.0)
    if peaks.size == 0:
        return 0.0, 0.0
    lag = int(peaks[int(np.argmax(properties["prominences"]))]) + min_lag

    teeth = [k * lag for k in (1, 2, 3) if k * lag < x.size]
    gaps = [int(round((k - 0.5) * lag)) for k in (1, 2, 3) if k * lag < x.size]
    score = float(np.mean(autocorr[teeth]) - np.mean(autocorr[gaps]))
    return float(np.clip(score, 0.0, 1.0)), float(lag * cadence)


def measure_region(
    context: FileContext,
    row0: int,
    row1: int,
    col0: int,
    col1: int,
    physics: BurstPhysics | None = None,
) -> dict[str, float]:
    """Every entry of :data:`REGION_FEATURES` for one region, as named floats."""
    n_freq, n_time = context.n_freq, context.n_time
    row0, row1 = max(0, int(row0)), min(n_freq, int(row1))
    col0, col1 = max(0, int(col0)), min(n_time, int(col1))
    n_rows, n_cols = max(1, row1 - row0), max(1, col1 - col0)

    values = {name: 0.0 for name in REGION_FEATURES}
    values["log_rows"] = math.log10(1.0 + n_rows) / 3.0
    values["log_cols"] = math.log10(1.0 + n_cols) / 5.0
    values["duration_fraction"] = n_cols / float(max(1, n_time))
    values["file_bright_fraction"] = math.sqrt(max(0.0, context.bright_fraction))
    values["file_noise"] = float(min(1.0, context.noise * 10.0))
    if context.freq_mhz is not None and row1 > row0:
        mid = 0.5 * float(context.freq_mhz[row0] + context.freq_mhz[row1 - 1])
        values["log_freq_mid"] = math.log10(1.0 + max(0.0, mid)) / 3.0
    if row1 <= row0 or col1 <= col0:
        values["faint"] = 1.0
        return values

    window = context.normalized[row0:row1, col0:col1]
    bright = context.bright[row0:row1, col0:col1]
    mask = bright
    level = context.level
    if int(mask.sum()) < MIN_REGION_PIXELS:
        # Faint region: measure its shape at a level relative to itself, and say
        # so, rather than reporting a featureless zero vector.
        level = max(FAINT_FLOOR, float(np.percentile(window, FAINT_PERCENTILE)))
        mask = window >= level
        values["faint"] = 1.0

    rows_with = np.flatnonzero(mask.any(axis=1))
    cols_with = np.flatnonzero(mask.any(axis=0))
    if rows_with.size == 0 or cols_with.size == 0:
        values["faint"] = 1.0
        return values

    # Weighted by how much of the region each channel or sample holds, so the
    # features describe its signal rather than the noise pixels at its edges.
    row_weight = mask[rows_with].sum(axis=1).astype(float)
    col_weight = mask[:, cols_with].sum(axis=0).astype(float)

    # Carriers: are these channels bright outside the region as well?
    inside = bright[rows_with].sum(axis=1)
    outside = (context.row_bright[row0 + rows_with] - inside) / float(max(1, n_time - n_cols))
    values["outside_persistence"] = float(
        np.clip(np.average(outside, weights=row_weight), 0.0, 1.0)
    )

    # Impulses and steps: how much of the band, and all at once?
    values["band_fraction"] = rows_with.size / float(n_freq)
    values["simultaneity"] = float(
        np.clip(
            np.average(context.col_bright[col0 + cols_with] / float(n_freq), weights=col_weight),
            0.0,
            1.0,
        )
    )

    # Drift shows up as a spread of onset times across channels.
    onset_s = mask[rows_with].argmax(axis=1) * context.cadence_s
    spread = float(np.percentile(onset_s, 90) - np.percentile(onset_s, 10))
    values["log_onset_spread"] = math.log10(1.0 + spread)

    # Thin tracks: sweeps and impulses in time, carriers in frequency.
    values["log_thickness_time"] = math.log10(
        1.0 + _run_thickness(mask[rows_with]) * context.cadence_s
    )
    values["log_thickness_freq"] = math.log10(1.0 + _run_thickness(mask[:, cols_with].T))

    values["fill_fraction"] = float(mask.sum()) / float(n_rows * n_cols)

    peak = float(np.percentile(window[mask], 99))
    snr = (peak - context.median) / max(context.noise, 1e-3)
    values["log_snr"] = math.log10(1.0 + max(0.0, snr)) / 3.0

    profile = window[rows_with].mean(axis=0)
    high, middle = float(np.percentile(profile, 95)), float(np.percentile(profile, 50))
    values["peakiness"] = float(np.clip((high - middle) / (high + 1e-6), 0.0, 1.0))

    # Periodicity over a window wide enough to hold several repetitions.
    pad = max(4 * n_cols, int(round(PERIODICITY_WINDOW_S / max(context.cadence_s, 1e-3))))
    w0, w1 = max(0, col0 - pad), min(n_time, col1 + pad)
    score, period = _periodicity(context.band_mean(row0, row1, w0, w1), context.cadence_s)
    values["periodicity"] = score
    values["log_period"] = math.log10(1.0 + period) / 2.0 if score > 0.2 else 0.0

    if context.rfi_rows is not None:
        values["rfi_flag_fraction"] = float(context.rfi_rows[row0 + rows_with].mean())

    count = (
        int(physics.burst_count)
        if physics is not None and physics.burst_count
        else count_bursts(window, level, context.cadence_s)
    )
    values["burst_count"] = min(count, 12) / 12.0
    return values


def region_vector(values: dict[str, float] | None) -> np.ndarray:
    """:data:`REGION_FEATURES` in their fixed order; zeros when not measured."""
    if not values:
        return np.zeros(len(REGION_FEATURES), dtype=np.float32)
    return np.array([float(values.get(name, 0.0)) for name in REGION_FEATURES], dtype=np.float32)


def feature_vector(physics: BurstPhysics | None, region: dict[str, float] | None) -> np.ndarray:
    """The ``region_v2`` feature input for one region: physics then region features."""
    return np.concatenate([physics_to_vector(physics), region_vector(region)]).astype(np.float32)


