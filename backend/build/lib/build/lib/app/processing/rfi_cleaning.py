"""RFI cleaning via percentile clipping."""
import numpy as np


def percentile_clip(data: np.ndarray, low: float = 1.0, high: float = 99.0) -> np.ndarray:
    """Clip values outside [low, high] percentile."""
    lo = np.nanpercentile(data, low)
    hi = np.nanpercentile(data, high)
    return np.clip(data, lo, hi)


def normalize(data: np.ndarray) -> np.ndarray:
    """Scale to [0, 1]."""
    lo, hi = data.min(), data.max()
    if hi == lo:
        return np.zeros_like(data)
    return (data - lo) / (hi - lo)
