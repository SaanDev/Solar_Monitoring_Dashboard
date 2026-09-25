"""Predicted Kp from L1 solar-wind measurements (Newell coupling function).

Pure functions (no DB, no I/O) so the forecast math is unit-testable.

The Newell et al. (2007) universal coupling function estimates the rate
magnetic flux is opened at the magnetopause:

    d(phi)/dt = v^(4/3) * Bt^(2/3) * sin^(8/3)(theta_c / 2)

with ``v`` the solar-wind speed (km/s), ``Bt`` the transverse IMF magnitude
sqrt(By^2 + Bz^2) (nT) and ``theta_c = atan2(|By|, Bz)`` the IMF clock angle —
zero for purely northward IMF (no coupling), pi for purely southward (maximum).

Kp is then estimated with the Newell et al. (2008) regression, which adds a
solar-wind pressure term:

    Kp = 0.05 + 2.244e-4 * d(phi)/dt + 2.844e-6 * sqrt(n) * v^2

(``n`` = proton density, cm^-3). Because Kp is a 3-hourly planetary index while
L1 data arrives at 1-minute cadence, the instantaneous estimate is smoothed
with a trailing 1-hour mean before being read as "the Kp this solar wind
implies for the next ~1-3 hours".
"""
from __future__ import annotations

import math
from datetime import datetime, timedelta

from app.processing.event_detection import KP_MIN_STORM, _spans
from app.processing.geomag_scale import kp_storm_scale

# Newell et al. (2008) regression coefficients (see module docstring).
_KP_BASE = 0.05
_KP_COUPLING_COEF = 2.244e-4
_KP_PRESSURE_COEF = 2.844e-6

# Trailing window that turns the 1-minute instantaneous estimate into a
# Kp-like quantity (Kp itself integrates hours of activity).
SMOOTHING_WINDOW = timedelta(hours=1)

# A predicted-storm episode tolerates a dropout this long before splitting
# (L1 feeds are 1-minute cadence, so this bridges brief data gaps only).
PREDICTION_MAX_GAP = timedelta(minutes=30)

_PREDICTION_URL = "https://www.swpc.noaa.gov/products/real-time-solar-wind"


def newell_coupling(
    speed: float | None, by: float | None, bz: float | None
) -> float | None:
    """d(phi)/dt for one sample, or ``None`` when an input is missing."""
    if speed is None or by is None or bz is None or speed <= 0:
        return None
    bt = math.hypot(by, bz)
    if bt == 0:
        return 0.0
    theta = math.atan2(abs(by), bz)  # clock angle in [0, pi]
    return speed ** (4 / 3) * bt ** (2 / 3) * math.sin(theta / 2) ** (8 / 3)


def predicted_kp(
    coupling: float | None, density: float | None, speed: float | None
) -> float | None:
    """Newell (2008) Kp estimate, clamped to the index's 0-9 range."""
    if coupling is None:
        return None
    kp = _KP_BASE + _KP_COUPLING_COEF * coupling
    if density is not None and density >= 0 and speed is not None:
        kp += _KP_PRESSURE_COEF * math.sqrt(density) * speed**2
    return min(max(kp, 0.0), 9.0)


def predict_series(points: list[dict]) -> list[dict]:
    """``[{time, speed, density, by, bz}]`` -> ``[{time, kp, coupling}]``.

    Instantaneous per-sample estimates; a sample missing IMF/speed yields
    ``kp=None`` (a gap, not a dropped point) so smoothing sees the cadence.
    """
    out: list[dict] = []
    for p in points:
        c = newell_coupling(p.get("speed"), p.get("by"), p.get("bz"))
        out.append(
            {
                "time": p["time"],
                "coupling": c,
                "kp": predicted_kp(c, p.get("density"), p.get("speed")),
            }
        )
    return out


def smooth_series(
    points: list[dict], keys: tuple[str, ...] = ("kp", "coupling"),
    window: timedelta = SMOOTHING_WINDOW,
) -> list[dict]:
    """Trailing-window mean of ``keys`` over time-ordered points.

    ``None`` values don't contribute; a point whose window holds no valid
    samples stays ``None``. O(n) via a sliding window.
    """
    out: list[dict] = []
    start = 0
    sums = {k: 0.0 for k in keys}
    counts = {k: 0 for k in keys}
    for i, p in enumerate(points):
        for k in keys:
            v = points[i].get(k)
            if v is not None:
                sums[k] += v
                counts[k] += 1
        while points[start]["time"] < p["time"] - window:
            for k in keys:
                v = points[start].get(k)
                if v is not None:
                    sums[k] -= v
                    counts[k] -= 1
            start += 1
        smoothed = {"time": p["time"]}
        for k in keys:
            smoothed[k] = (sums[k] / counts[k]) if counts[k] else None
        out.append(smoothed)
    return out


def predicted_storm_events(samples: list[tuple[datetime, float | None]]) -> list[dict]:
    """Segment a smoothed predicted-Kp series into predicted-storm events.

    A contiguous span with predicted Kp at/above the G1 onset becomes one
    ``geomagnetic_storm_prediction`` event (same span semantics as the real
    detectors: a span running to the latest sample is ongoing).
    """
    out = []
    for s in _spans(samples, lambda v: v >= KP_MIN_STORM, PREDICTION_MAX_GAP):
        scale = kp_storm_scale(s["peak_value"]) or "G1"
        out.append(
            {
                "type": "geomagnetic_storm_prediction",
                "severity": scale,
                "description": (
                    f"Predicted geomagnetic storm {scale} - solar-wind coupling "
                    f"implies Kp ~{s['peak_value']:.1f} (Newell)"
                ),
                "source_url": _PREDICTION_URL,
                **s,
            }
        )
    return out
