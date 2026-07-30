"""Bright-region proposals for the burst-type stage.

Ported from the CALLISTO Trainer (``services/assist.py`` and ``core/inference.py``).

CCMT is a *classifier*, not a detector: given a region it names the burst type,
but it has no notion of where a burst is and no background class. So candidate
regions come from plain signal processing — threshold the normalized spectrum,
group connected pixels, keep blobs of a plausible size — and CCMT is then asked
to type each candidate.

This finder is deliberately **not** trusted on its own. It fires on RFI, carrier
lines and calibration artifacts as readily as on solar bursts, and produces
candidates even in quiet files. That is why typing only runs on files a binary
model (CCM) has already called ``Burst``: the binary gate decides *whether*
there is a burst, these regions and CCMT only decide *what kind* and *where*.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Sequence

import numpy as np

logger = logging.getLogger(__name__)

# Thresholds are in normalized [0, 1] units, where 0 maps to -1 dB and 1 to
# +8 dB above background.
DEFAULT_REGION_THRESHOLD = 0.35   # ~+2.2 dB, "clearly above noise"
DEFAULT_MIN_AREA = 60             # pixels; rejects single hot samples and specks
DEFAULT_MAX_REGIONS = 8
# Minimum extent for a region to be worth typing, in pixels. CCMT was trained on
# hand-drawn boxes no smaller than 12 frequency rows x 9 time samples, so a
# narrower region is out of distribution and gets a confident, meaningless class.
#
# This filter is what keeps the type stage usable. e-CALLISTO files carry a
# periodic narrow-band calibration marker — a couple of frequency channels at a
# band edge, repeating every ~60 s — which clears the brightness threshold and
# the area floor in almost every file. Left in, a dozen of those blobs fill every
# candidate slot and crowd out the actual burst, so a genuine Type III file comes
# back typed from an artifact instead. Requiring a real frequency sweep (which is
# what defines a Type II/III burst) removes them.
DEFAULT_MIN_ROWS = 12
DEFAULT_MIN_COLS = 9
# Adaptive cap: a spectrum whose brightest pixels sit well below the absolute
# threshold would yield nothing at all, so the threshold drops toward its own
# high percentile — but never below the floor, which keeps noise out.
ADAPTIVE_PERCENTILE = 99.9
ADAPTIVE_FLOOR = 0.15


@dataclass
class Region:
    """A candidate burst region in pixel coordinates (half-open box)."""

    row0: int          # frequency-channel index, inclusive
    row1: int          # exclusive
    col0: int          # time-sample index, inclusive
    col1: int          # exclusive
    area: int          # connected pixels above threshold
    peak: float        # brightest normalized value in the region
    burst_type: str | None = None
    confidence: float | None = None
    probabilities: dict[str, float] = field(default_factory=dict)

    def as_box(self) -> tuple[int, int, int, int]:
        return self.row0, self.row1, self.col0, self.col1


def resolve_threshold(
    normalized: np.ndarray,
    absolute: float = DEFAULT_REGION_THRESHOLD,
    adaptive: bool = True,
    percentile: float = ADAPTIVE_PERCENTILE,
    floor: float = ADAPTIVE_FLOOR,
) -> float:
    """The brightness threshold to use for one spectrum.

    Adaptive mode never *raises* the threshold above ``absolute`` — it only
    lowers it, bounded by ``floor``, so a faint-but-real burst in a low-contrast
    file still produces regions.
    """
    if not adaptive:
        return float(absolute)
    value = float(np.percentile(normalized, percentile))
    return float(min(float(absolute), max(float(floor), value)))


def _label_connected(mask: np.ndarray) -> tuple[np.ndarray, int]:
    """Label 8-connected components. SciPy is a core dependency."""
    from scipy import ndimage

    return ndimage.label(mask, structure=np.ones((3, 3), dtype=int))


def find_candidate_regions(
    normalized: np.ndarray,
    threshold: float = DEFAULT_REGION_THRESHOLD,
    min_area: int = DEFAULT_MIN_AREA,
    max_candidates: int = DEFAULT_MAX_REGIONS,
    min_rows: int = DEFAULT_MIN_ROWS,
    min_cols: int = DEFAULT_MIN_COLS,
) -> list[Region]:
    """Propose bright connected regions, largest first.

    A heuristic, not a detector: it finds *bright things*, which include RFI,
    calibration spikes and instrument artifacts as readily as solar bursts. The
    geometry floors (``min_rows`` / ``min_cols``) drop candidates too small to be
    in CCMT's training distribution — see :data:`DEFAULT_MIN_ROWS`. They are
    applied *before* the top-N cut so a real burst is never crowded out by a
    swarm of artifacts.
    """
    if normalized.ndim != 2:
        raise ValueError(f"Expected a 2D normalized spectrum, got {normalized.shape}")

    mask = normalized >= float(threshold)
    if not mask.any():
        return []

    labels, count = _label_connected(mask)
    if count == 0:
        return []

    # One pass over the label image is much cheaper than slicing per component.
    areas = np.bincount(labels.ravel())
    regions: list[Region] = []
    for component in range(1, count + 1):
        if areas[component] < min_area:
            continue
        rows, cols = np.nonzero(labels == component)
        row0, row1 = int(rows.min()), int(rows.max()) + 1
        col0, col1 = int(cols.min()), int(cols.max()) + 1
        if (row1 - row0) < min_rows or (col1 - col0) < min_cols:
            continue
        regions.append(
            Region(
                row0=row0,
                row1=row1,
                col0=col0,
                col1=col1,
                area=int(areas[component]),
                peak=float(normalized[rows, cols].max()),
            )
        )

    regions.sort(key=lambda r: r.area, reverse=True)
    return regions[:max_candidates]


def dominant_type(regions: Sequence[Region]) -> str | None:
    """The type of the largest confidently-typed region.

    Area rather than confidence: a big region is more likely to be the actual
    event, while a small bright speck is more likely interference that the
    classifier still had to put in *some* class.
    """
    typed = [r for r in regions if r.burst_type]
    if not typed:
        return None
    return max(typed, key=lambda r: r.area).burst_type


def _row_to_mhz(
    row: float, n_freq: int, freq_axis: np.ndarray | None,
    freq_min: float | None, freq_max: float | None,
) -> float | None:
    """Map a fractional frequency-row index to MHz.

    Uses the per-row FREQUENCY axis when the FITS file carried one; otherwise
    interpolates between the file's frequency bounds, remembering that row 0 is
    the **highest** frequency (the axis is stored descending).
    """
    if freq_axis is not None and freq_axis.size:
        index = int(np.clip(round(row), 0, freq_axis.size - 1))
        return float(freq_axis[index])
    if freq_min is None or freq_max is None or n_freq <= 1:
        return None
    fraction = float(np.clip(row / (n_freq - 1), 0.0, 1.0))
    return float(freq_max - fraction * (freq_max - freq_min))


def region_to_axes(
    region: Region, metadata: dict[str, Any], segment_seconds: int
) -> dict[str, Any]:
    """Describe a region in physical units for display.

    Frequencies in MHz (low/high, ordered), and time as seconds from the
    segment's start — the segment length is passed in because e-CALLISTO cadence
    varies (0.25 s over 3600 samples, 0.5 s over 1800).
    """
    n_freq = int(metadata.get("n_freq") or 0)
    n_time = int(metadata.get("n_time") or 0)
    freq_axis = metadata.get("freq_axis")
    freq_min = metadata.get("freq_min_mhz")
    freq_max = metadata.get("freq_max_mhz")

    edge_a = _row_to_mhz(region.row0, n_freq, freq_axis, freq_min, freq_max)
    edge_b = _row_to_mhz(region.row1 - 1, n_freq, freq_axis, freq_min, freq_max)
    if edge_a is not None and edge_b is not None:
        low, high = sorted((edge_a, edge_b))
    else:
        low = high = None

    if n_time > 1:
        scale = segment_seconds / n_time
        start_seconds = int(region.col0 * scale)
        end_seconds = int(np.ceil(region.col1 * scale))
    else:
        start_seconds = 0
        end_seconds = segment_seconds

    return {
        "freq_min_mhz": low,
        "freq_max_mhz": high,
        "start_seconds": start_seconds,
        "end_seconds": min(end_seconds, segment_seconds),
        "burst_type": region.burst_type,
        "confidence": region.confidence,
        "area": region.area,
    }
