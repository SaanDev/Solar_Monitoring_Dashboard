"""Burst physics measured from a region's own pixels — CCM v2.0's first 8 features.

Ported from the CALLISTO Trainer (``core/burst_physics.py``, the model-feature
half only). Frequency drift rate is the quantity that physically separates the
burst types — a Type III electron beam drifts tens of MHz/s, a Type II shock two
orders of magnitude slower — so the model is told it directly rather than left to
infer it from a resampled 224x224 image.

Every candidate region is measured the same way, background and interference
included (a value present only for bursts would teach the model the label):

1. threshold inside the region, relative to its own content;
2. keep the largest connected component — the burst, not whatever else is bright;
3. track its ridge along whichever axis it spans more of;
4. fit with Theil-Sen (median of pairwise slopes), which ignores the outliers
   interference and edge effects inject.

An unmeasurable region becomes an all-zero vector with the ``measured`` flag off,
so the network can tell "no measurement" from "drift of zero".
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from app.ml.preprocessing import SpectrumAxes

# Fraction of the region's own bright tail used as the burst level; relative
# because station gain varies by orders of magnitude.
BURST_PERCENTILE = 93.0
# Never below this in normalized units (~+1.7 dB), or noise becomes "burst".
MIN_BURST_LEVEL = 0.30
# Fewer usable samples than this and a fitted slope is not a measurement.
MIN_TRACK_SAMPLES = 5
# Burst counting: a gap shorter than BURST_GAP_S inside one lane is closed, and a
# run shorter than MIN_BURST_RUN_S is not a burst. In seconds so the rule does
# not change with a station's cadence.
BURST_GAP_S = 0.5
MIN_BURST_RUN_S = 0.5
# A channel bright for more than this fraction of the time outside a region is a
# carrier, not part of a burst.
CARRIER_PERSISTENCE = 0.3

# Order is fixed: it defines the model's physics input.
PHYSICS_FEATURES = (
    "log_freq_start",
    "log_freq_end",
    "log_bandwidth",
    "log_duration",
    "signed_log_drift",
    "signed_log_relative_drift",
    "fit_quality",
    "measured",
)
NUM_PHYSICS_FEATURES = len(PHYSICS_FEATURES)


@dataclass
class BurstPhysics:
    """Physical parameters measured from one region."""

    freq_start_mhz: float | None = None   # at the burst's first moment
    freq_end_mhz: float | None = None     # at its last moment
    freq_high_mhz: float | None = None
    freq_low_mhz: float | None = None
    time_start_s: float | None = None
    time_end_s: float | None = None
    duration_s: float | None = None
    bandwidth_mhz: float | None = None
    # Negative is the normal high-to-low progression.
    drift_mhz_per_s: float | None = None
    relative_drift_per_s: float | None = None  # (1/f)(df/dt), comparable across bands
    fit_quality: float | None = None      # |Spearman rho| of the tracked ridge
    track_samples: int = 0
    track_axis: str = ""                  # "time" or "frequency"
    confidence: str = "none"              # good | fair | poor | none
    # Separate bursts in the region: 1 for a single Type III, 3+ for a group.
    burst_count: int = 0

    @property
    def measured(self) -> bool:
        return self.drift_mhz_per_s is not None


def _largest_component(mask: np.ndarray) -> np.ndarray:
    """Keep only the biggest 8-connected blob, i.e. the burst itself."""
    from scipy import ndimage

    if not mask.any():
        return mask
    labels, count = ndimage.label(mask, structure=np.ones((3, 3), dtype=int))
    if count <= 1:
        return mask
    sizes = np.bincount(labels.ravel())
    sizes[0] = 0
    return labels == int(sizes.argmax())


def _theil_sen(x: np.ndarray, y: np.ndarray) -> float | None:
    """Median of pairwise slopes over every pair with a positive x step.

    None when every ``x`` is the same: a track confined to one time sample has
    no slope.
    """
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    if x.size < 2 or float(np.ptp(x)) == 0.0:
        return None
    dx = x[:, np.newaxis] - x
    dy = y[:, np.newaxis] - y
    rising = dx > 0
    return float(np.median(dy[rising] / dx[rising]))


def _spearman(x: np.ndarray, y: np.ndarray) -> float:
    """Rank correlation: how monotonic the tracked ridge is."""
    if x.size < 3:
        return 0.0
    # A constant track has no defined correlation (a perfectly horizontal
    # ridge) — a real outcome, not an error.
    if np.ptp(x) == 0 or np.ptp(y) == 0:
        return 0.0
    try:
        from scipy import stats

        result = stats.spearmanr(x, y)
        value = float(getattr(result, "statistic", result[0]))
    except Exception:
        return 0.0
    return 0.0 if math.isnan(value) else abs(value)


def _grade(quality: float, samples: int) -> str:
    if samples >= 12 and quality >= 0.8:
        return "good"
    if samples >= MIN_TRACK_SAMPLES and quality >= 0.5:
        return "fair"
    return "poor"


def _ridge(
    positions: np.ndarray,
    values: np.ndarray,
    weights: np.ndarray,
    unique_positions: np.ndarray,
    axis_values: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """Intensity-weighted centroid at each position along one axis, in physical units."""
    axis_values = np.asarray(axis_values, dtype=float)
    coordinates: list[float] = []
    centroids: list[float] = []
    for position in unique_positions:
        selected = positions == position
        weight = weights[selected]
        total = float(weight.sum())
        if total <= 0:
            continue
        coordinates.append(float(axis_values[min(int(position), axis_values.size - 1)]))
        centroids.append(float((values[selected] * weight).sum() / total))
    return np.asarray(coordinates, dtype=float), np.asarray(centroids, dtype=float)


def cadence_seconds(axes: SpectrumAxes | None, default: float = 0.25) -> float:
    """Median time step of a spectrum, in seconds."""
    if axes is None or axes.n_time < 2:
        return default
    step = float(np.median(np.diff(np.asarray(axes.time_s, dtype=float))))
    return step if math.isfinite(step) and step > 0 else default


def carrier_rows(
    normalized: np.ndarray, row0: int, row1: int, col0: int, col1: int, level: float
) -> np.ndarray:
    """Channels of a region that stay bright across the rest of the recording."""
    rows = np.asarray(normalized[row0:row1]) >= float(level)
    outside = rows.sum(axis=1) - rows[:, col0:col1].sum(axis=1)
    span = max(1, normalized.shape[1] - (col1 - col0))
    return outside / span > CARRIER_PERSISTENCE


def count_bursts(
    window: np.ndarray,
    level: float,
    cadence_s: float = 0.25,
    skip_rows: np.ndarray | None = None,
) -> int:
    """Number of separate bursts in a region, counted along time.

    A group of Type III bursts is several bright lanes one after another, so any
    channel crossing it sees one run of bright samples per lane; the median of
    the per-channel run counts is indifferent to drift. ``skip_rows`` leaves out
    carriers, whose on-periods would otherwise each count as a run.
    """
    mask = np.asarray(window) >= float(level)
    if skip_rows is not None:
        mask = mask & ~np.asarray(skip_rows, dtype=bool)[:, None]
    if mask.ndim != 2 or not mask.any():
        return 0
    cadence = cadence_s if cadence_s and cadence_s > 0 else 0.25
    gap = max(1, int(round(BURST_GAP_S / cadence)))
    min_run = max(2, int(round(MIN_BURST_RUN_S / cadence)))

    counts: list[int] = []
    for row in mask:
        if not row.any():
            continue
        edges = np.flatnonzero(np.diff(np.concatenate(([0], row.astype(np.int8), [0]))))
        starts, ends = edges[0::2], edges[1::2]
        if starts.size > 1:
            # A boundary between two runs survives only when the gap is long.
            separate = (starts[1:] - ends[:-1]) > gap
            starts = np.concatenate((starts[:1], starts[1:][separate]))
            ends = np.concatenate((ends[:-1][separate], ends[-1:]))
        runs = int(((ends - starts) >= min_run).sum())
        if runs:
            counts.append(runs)
    if not counts:
        return 0
    return int(math.floor(float(np.median(counts)) + 0.5))


def measure_burst(
    normalized: np.ndarray,
    axes: SpectrumAxes,
    row0: int,
    row1: int,
    col0: int,
    col1: int,
    percentile: float = BURST_PERCENTILE,
    min_level: float = MIN_BURST_LEVEL,
) -> BurstPhysics:
    """Measure a region's extent and drift rate from its pixels (see module docs)."""
    physics = BurstPhysics()

    row0 = max(0, int(row0))
    col0 = max(0, int(col0))
    row1 = min(int(normalized.shape[0]), int(row1))
    col1 = min(int(normalized.shape[1]), int(col1))
    if row1 - row0 < 2 or col1 - col0 < 2:
        return physics

    window = normalized[row0:row1, col0:col1]
    if not np.isfinite(window).any():
        return physics

    level = max(float(min_level), float(np.percentile(window, percentile)))
    # Counted over every bright pixel, before the largest-component step below
    # throws away all but one lane of a group — but not over carriers.
    physics.burst_count = count_bursts(
        window, level, cadence_seconds(axes),
        skip_rows=carrier_rows(normalized, row0, row1, col0, col1, level),
    )
    mask = _largest_component(window >= level)
    if mask.sum() < MIN_TRACK_SAMPLES:
        return physics

    rows, cols = np.nonzero(mask)
    abs_rows, abs_cols = rows + row0, cols + col0
    freqs = np.asarray(axes.freq_mhz, dtype=float)[np.clip(abs_rows, 0, axes.n_freq - 1)]
    times = np.asarray(axes.time_s, dtype=float)[np.clip(abs_cols, 0, axes.n_time - 1)]

    physics.freq_high_mhz = float(freqs.max())
    physics.freq_low_mhz = float(freqs.min())
    physics.time_start_s = float(times.min())
    physics.time_end_s = float(times.max())
    physics.duration_s = physics.time_end_s - physics.time_start_s
    physics.bandwidth_mhz = physics.freq_high_mhz - physics.freq_low_mhz

    # Track along whichever axis the burst actually spans: a near-vertical Type
    # III covers many rows but few columns, so a per-column fit would have almost
    # nothing to fit and the transpose is well conditioned.
    unique_cols = np.unique(abs_cols)
    unique_rows = np.unique(abs_rows)
    weights = window[rows, cols]
    if unique_cols.size >= unique_rows.size:
        physics.track_axis = "time"
        track_t, track_f = _ridge(abs_cols, freqs, weights, unique_cols, axes.time_s)
    else:
        physics.track_axis = "frequency"
        track_f, track_t = _ridge(abs_rows, times, weights, unique_rows, axes.freq_mhz)

    physics.track_samples = int(track_t.size)
    if track_t.size < MIN_TRACK_SAMPLES:
        return physics
    if float(np.ptp(track_t)) == 0.0:
        return physics
    slope = _theil_sen(track_t, track_f)
    if slope is None or not math.isfinite(slope):
        return physics

    physics.drift_mhz_per_s = float(slope)
    physics.fit_quality = _spearman(track_t, track_f)
    physics.confidence = _grade(physics.fit_quality, physics.track_samples)

    # Start/end frequency from the fitted track, clamped to what was observed so
    # the fit cannot extrapolate beyond the data.
    order = np.argsort(track_t)
    first_t, last_t = float(track_t[order[0]]), float(track_t[order[-1]])
    intercept = float(np.median(track_f - slope * track_t))
    span = (physics.freq_low_mhz, physics.freq_high_mhz)
    physics.freq_start_mhz = float(np.clip(slope * first_t + intercept, *span))
    physics.freq_end_mhz = float(np.clip(slope * last_t + intercept, *span))

    mid_freq = 0.5 * (physics.freq_high_mhz + physics.freq_low_mhz)
    if mid_freq > 0:
        # Type III drift scales as ~f^1.84, so the relative rate is the one that
        # is comparable between a 400 MHz and a 40 MHz observation.
        physics.relative_drift_per_s = float(slope / mid_freq)
    return physics


def _signed_log(value: float, scale: float = 1.0) -> float:
    """Compress a signed quantity spanning decades, keeping its sign."""
    return float(math.copysign(math.log10(1.0 + abs(value) / scale), value))


def physics_to_vector(physics: BurstPhysics | None) -> np.ndarray:
    """:data:`PHYSICS_FEATURES` as float32; zeros with ``measured`` off when unmeasured."""
    if physics is None or not physics.measured:
        return np.zeros(NUM_PHYSICS_FEATURES, dtype=np.float32)
    return np.array(
        [
            math.log10(1.0 + max(0.0, physics.freq_start_mhz or 0.0)),
            math.log10(1.0 + max(0.0, physics.freq_end_mhz or 0.0)),
            math.log10(1.0 + max(0.0, physics.bandwidth_mhz or 0.0)),
            math.log10(1.0 + max(0.0, physics.duration_s or 0.0)),
            _signed_log(physics.drift_mhz_per_s or 0.0, scale=0.01),
            _signed_log(physics.relative_drift_per_s or 0.0, scale=0.0001),
            float(physics.fit_quality or 0.0),
            1.0,
        ],
        dtype=np.float32,
    )
