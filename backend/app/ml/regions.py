"""Candidate regions: where in a spectrum CCM v2.0 is asked to look.

Ported from the CALLISTO Trainer (``core/region_finder.py``). A plain
signal-processing pass — threshold the normalized spectrum, grow each bright
seed through its faint surroundings, keep blobs of a plausible size. It is **not**
a detector: it finds *bright things*, and interference, carrier lines and
calibration artifacts qualify as readily as solar bursts. Telling them apart is
the model's job — it has background and RFI classes of its own — which is why the
finder must run with exactly the settings the model's training regions were
mined and its burst threshold was calibrated with. Those settings come from the
checkpoint (``inference.region_finder``), never from configuration.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from app.ml.preprocessing import PixelBox, SpectrumAxes, box_to_physical

# 0.35 in normalized units is about +2.2 dB above background.
DEFAULT_REGION_THRESHOLD = 0.35
DEFAULT_MIN_AREA = 60
DEFAULT_MAX_REGIONS = 24
# Adaptive thresholding: station gain varies enormously, so the threshold drops
# toward the file's own 99.9th percentile — never above the absolute setting and
# never below the floor, so it relaxes for faint files without chasing noise.
ADAPTIVE_PERCENTILE = 99.9
ADAPTIVE_FLOOR = 0.15
# Hysteresis: pixels at the threshold are seeds, grown through the connected
# pixels of a lightly smoothed copy that reach HYSTERESIS x the threshold. A
# faint drifting lane otherwise crosses the threshold only in fragments, each
# under the minimum area.
DEFAULT_HYSTERESIS = 0.65
HYSTERESIS_SMOOTH = 3
MIN_SEED_PIXELS = 5


@dataclass
class Region:
    """A candidate region in pixel coordinates (half-open box)."""

    row0: int          # frequency-channel index, inclusive
    row1: int          # exclusive
    col0: int          # time-sample index, inclusive
    col1: int          # exclusive
    area: int          # pixels at or above the (low) level
    peak: float        # brightest normalized value in the region

    def as_box(self) -> PixelBox:
        return PixelBox(self.row0, self.row1, self.col0, self.col1)


def resolve_threshold(
    normalized: np.ndarray,
    absolute: float = DEFAULT_REGION_THRESHOLD,
    adaptive: bool = True,
    percentile: float = ADAPTIVE_PERCENTILE,
    floor: float = ADAPTIVE_FLOOR,
) -> float:
    """The brightness threshold to use for one spectrum."""
    if not adaptive:
        return float(absolute)
    value = float(np.percentile(normalized, percentile))
    return float(min(float(absolute), max(float(floor), value)))


def find_candidate_regions(
    normalized: np.ndarray,
    threshold: float = DEFAULT_REGION_THRESHOLD,
    min_area: int = DEFAULT_MIN_AREA,
    max_candidates: int = DEFAULT_MAX_REGIONS,
    hysteresis: float | None = DEFAULT_HYSTERESIS,
    min_seed: int = MIN_SEED_PIXELS,
) -> list[Region]:
    """Propose bright connected regions, largest first.

    With ``hysteresis`` a region is a component of the smoothed spectrum above
    ``hysteresis * threshold`` holding at least ``min_seed`` pixels above
    ``threshold``; its box, area and peak are taken over its own pixels above the
    lower level, so smoothing never widens it. With ``hysteresis=None`` it is a
    plain component above ``threshold``.
    """
    from scipy import ndimage

    if normalized.ndim != 2:
        raise ValueError(f"Expected a 2D normalized spectrum, got {normalized.shape}")

    seeds = normalized >= float(threshold)
    if not seeds.any():
        return []
    structure = np.ones((3, 3), dtype=int)

    if hysteresis is not None:
        low_level = float(threshold) * float(hysteresis)
        smoothed = ndimage.uniform_filter(
            np.asarray(normalized, dtype=np.float32), size=HYSTERESIS_SMOOTH
        )
        labels, count = ndimage.label((smoothed >= low_level) | seeds, structure=structure)
        if count == 0:
            return []
        own = np.where(normalized >= low_level, labels, 0)
        areas = np.bincount(own.ravel(), minlength=count + 1)
        seed_counts = np.bincount(labels[seeds], minlength=count + 1)
        keep = np.flatnonzero((areas[1:] >= min_area) & (seed_counts[1:] >= min_seed)) + 1
        measured = own
    else:
        labels, count = ndimage.label(seeds, structure=structure)
        if count == 0:
            return []
        areas = np.bincount(labels.ravel(), minlength=count + 1)
        keep = np.flatnonzero(areas[1:] >= min_area) + 1
        measured = labels

    if keep.size == 0:
        return []
    # One pass for every bounding box and peak: slicing the label image once per
    # component is a full-array scan each, which on a noisy recording with
    # hundreds of blobs takes seconds.
    slices = ndimage.find_objects(measured)
    peaks = np.atleast_1d(ndimage.maximum(normalized, measured, index=keep))
    regions = []
    for component, peak in zip(keep, peaks):
        rows, cols = slices[component - 1]
        regions.append(
            Region(
                row0=int(rows.start),
                row1=int(rows.stop),
                col0=int(cols.start),
                col1=int(cols.stop),
                area=int(areas[component]),
                peak=float(peak),
            )
        )
    regions.sort(key=lambda r: r.area, reverse=True)
    return regions[:max_candidates]


def region_to_axes(region: Region, axes: SpectrumAxes) -> dict[str, Any]:
    """A region's extent for display: MHz, and seconds from the segment start.

    Frequencies are only reported from a real ``AXES`` table; the header fallback
    is a placeholder (usually a channel index) that would read as nonsense MHz.
    """
    bounds = box_to_physical(axes, region.row0, region.row1, region.col0, region.col1)
    real_freq = axes.source == "axes_table"
    return {
        "freq_min_mhz": bounds["freq_lo_mhz"] if real_freq else None,
        "freq_max_mhz": bounds["freq_hi_mhz"] if real_freq else None,
        "start_seconds": int(np.floor(bounds["t_start_s"])),
        "end_seconds": int(np.ceil(bounds["t_end_s"])),
        "area": region.area,
    }
