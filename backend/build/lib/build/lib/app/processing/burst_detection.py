"""First-level solar radio burst candidate detection."""
from dataclasses import dataclass
import numpy as np
from scipy import ndimage


@dataclass
class BurstRegion:
    t_start_s: float
    t_end_s: float
    f_start_mhz: float
    f_end_mhz: float
    peak_intensity: float
    classification: str
    confidence: float


def detect_bursts(
    data: np.ndarray,
    time_axis: np.ndarray,
    freq_axis: np.ndarray,
    threshold_sigma: float = 3.0,
    min_pixels: int = 20,
) -> list[BurstRegion]:
    """
    Detect burst candidates in a cleaned, normalized dynamic spectrum.

    data shape: (n_freq, n_time), values in [0, 1].
    """
    mean = np.nanmean(data)
    std = np.nanstd(data)
    if std == 0:
        return []

    mask = data > (mean + threshold_sigma * std)
    labeled, n_features = ndimage.label(mask)

    regions: list[BurstRegion] = []
    for label_id in range(1, n_features + 1):
        coords = np.argwhere(labeled == label_id)
        if len(coords) < min_pixels:
            continue

        f_indices = coords[:, 0]
        t_indices = coords[:, 1]

        t_start = float(time_axis[t_indices.min()])
        t_end = float(time_axis[t_indices.max()])
        f_start = float(freq_axis[f_indices.max()])  # freq_axis may be descending
        f_end = float(freq_axis[f_indices.min()])
        peak = float(data[coords[:, 0], coords[:, 1]].max())

        classification, confidence = _classify(t_end - t_start, f_start, f_end, coords)
        regions.append(
            BurstRegion(
                t_start_s=t_start,
                t_end_s=t_end,
                f_start_mhz=min(f_start, f_end),
                f_end_mhz=max(f_start, f_end),
                peak_intensity=peak,
                classification=classification,
                confidence=confidence,
            )
        )

    return regions


def _classify(
    duration_s: float,
    f_start: float,
    f_end: float,
    coords: np.ndarray,
) -> tuple[str, float]:
    freq_range = abs(f_end - f_start)

    # Type III: short (<30 s), broad frequency drift
    if duration_s < 30 and freq_range > 50:
        return "Possible Type III", 0.6

    # Type II: long (>60 s), narrow band, slow drift
    if duration_s > 60 and freq_range < 100:
        return "Possible Type II", 0.5

    # Type IV: long (>5 min), broad band, continuum
    if duration_s > 300 and freq_range > 100:
        return "Possible Type IV", 0.4

    # Large but doesn't fit burst patterns → likely RFI
    if freq_range > 200:
        return "Possible RFI", 0.7

    return "Unclassified", 0.3
