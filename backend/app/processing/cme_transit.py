"""Drag-Based Model (DBM) for CME Sun->Earth transit — pure, unit-testable.

NASA DONKI ships a WSA-ENLIL ``estimatedShockArrivalTime`` only for the CMEs an
analyst has run the model on; most catalogued CMEs carry a measured cone speed
but no arrival estimate. This module computes an *independent, always-available*
arrival from the CME's own kinematics using the analytic Drag-Based Model
(Vrsnak et al. 2013, Solar Phys. 285).

Beyond ~20 solar radii a CME's dynamics are dominated by aerodynamic drag toward
the ambient solar wind:

    a(t) = -gamma * (v - w) * |v - w|

with ``gamma`` the drag parameter (km^-1) and ``w`` the ambient wind speed. With
constant ``gamma``/``w`` this integrates in closed form (u0 = v0 - w):

    v(t) = w + u0 / (1 + gamma*|u0|*t)
    r(t) = r0 + w*t + sign(u0) * (1/gamma) * ln(1 + gamma*|u0|*t)

``r(t)`` is monotonic increasing (v stays positive for any realistic CME), so the
arrival time — ``r(t) = 1 AU`` — is found by a robust bisection rather than
inverting the transcendental ``r(t)``. The launch point r0 = 21.5 Rs maps exactly
onto DONKI's cone-fit ``speed``/``time21_5``.

Pure functions (no I/O, no DB) mirroring ``event_detection`` / ``kp_prediction``
so the physics stays unit-testable; the ambient wind ``w`` is fed in by the
service layer (the live NOAA solar-wind speed).
"""
from __future__ import annotations

import math
from datetime import datetime, timedelta
from typing import Optional

# ── Physical constants ───────────────────────────────────────────────────────
RS_KM = 695_700.0          # solar radius, km
AU_RS = 214.94             # 1 AU in solar radii (149.6e6 km / RS_KM)
R0_RS = 21.5               # DBM launch height = DONKI cone-fit height (Rs)

# Drag parameter gamma (km^-1). Vrsnak et al. (2013) find 0.2e-7 typical for an
# average CME in average wind; the 0.1e-7 - 0.5e-7 spread (fast/dense CMEs drag
# harder) brackets the arrival-time uncertainty.
GAMMA_NOMINAL = 0.2e-7
GAMMA_LOW = 0.1e-7
GAMMA_HIGH = 0.5e-7

# Ambient solar-wind fallback when the live feed is unavailable (km/s).
W_DEFAULT = 400.0

# A CME with v0 > 0 in w > 0 always reaches 1 AU; cap the search so a pathological
# input can't loop unbounded (a ~250 km/s CME crosses 1 AU in ~7 days).
_MAX_TRANSIT_S = 12 * 86_400.0


def _r_of_t(t_s: float, v0: float, w: float, gamma: float, r0_km: float) -> float:
    """CME heliocentric distance (km) at ``t_s`` seconds after launch."""
    u0 = v0 - w
    if u0 == 0.0:
        return r0_km + w * t_s
    drag = gamma * abs(u0) * t_s
    return r0_km + w * t_s + math.copysign(1.0, u0) * (1.0 / gamma) * math.log1p(drag)


def _v_of_t(t_s: float, v0: float, w: float, gamma: float) -> float:
    """CME speed (km/s) at ``t_s`` seconds after launch."""
    u0 = v0 - w
    return w + u0 / (1.0 + gamma * abs(u0) * t_s)


def dbm_arrival(
    v0_km_s: float,
    t0: datetime,
    w_km_s: float = W_DEFAULT,
    gamma_per_km: float = GAMMA_NOMINAL,
    r0_rs: float = R0_RS,
    target_rs: float = AU_RS,
) -> Optional[dict]:
    """Predict CME arrival at ``target_rs`` (default 1 AU) via the analytic DBM.

    ``v0_km_s`` / ``t0`` are the cone-fit radial speed and time at ``r0_rs``
    (DONKI ``speed`` / ``time21_5``); ``w_km_s`` is the ambient wind speed.
    Returns ``{arrival_time, transit_hours, impact_speed_km_s}``, or ``None`` when
    the inputs are unusable (non-positive/zero launch speed) or 1 AU isn't reached
    inside the search cap.
    """
    if v0_km_s is None or v0_km_s <= 0:
        return None
    w = w_km_s if (w_km_s and w_km_s > 0) else W_DEFAULT
    gamma = gamma_per_km if gamma_per_km > 0 else GAMMA_NOMINAL
    r0_km = r0_rs * RS_KM
    target_km = target_rs * RS_KM
    if target_km <= r0_km:
        return None

    # r(t) is monotonic increasing; bisect for r(t) = target.
    lo, hi = 0.0, _MAX_TRANSIT_S
    if _r_of_t(hi, v0_km_s, w, gamma, r0_km) < target_km:
        return None  # too slow to reach 1 AU within the cap
    for _ in range(100):
        mid = 0.5 * (lo + hi)
        if _r_of_t(mid, v0_km_s, w, gamma, r0_km) < target_km:
            lo = mid
        else:
            hi = mid
    t_arr = 0.5 * (lo + hi)
    return {
        "arrival_time": t0 + timedelta(seconds=t_arr),
        "transit_hours": t_arr / 3600.0,
        "impact_speed_km_s": _v_of_t(t_arr, v0_km_s, w, gamma),
    }


def arrival_window(
    v0_km_s: float,
    t0: datetime,
    w_km_s: float = W_DEFAULT,
    r0_rs: float = R0_RS,
    target_rs: float = AU_RS,
) -> Optional[dict]:
    """Nominal arrival plus an earliest/latest bracket.

    The bracket runs the DBM over the drag-parameter spread and a +/-25% ambient
    wind span (min floored at 250 km/s); ``earliest`` / ``latest`` are the min /
    max predicted arrival across those corners. Returns the ``dbm_arrival`` dict
    for the nominal case augmented with ``arrival_earliest`` / ``arrival_latest``,
    or ``None`` when the nominal case is unusable.
    """
    nominal = dbm_arrival(v0_km_s, t0, w_km_s, GAMMA_NOMINAL, r0_rs, target_rs)
    if nominal is None:
        return None
    w = w_km_s if (w_km_s and w_km_s > 0) else W_DEFAULT
    arrivals = [nominal["arrival_time"]]
    for gamma in (GAMMA_LOW, GAMMA_HIGH):
        for wc in (max(250.0, w * 0.75), w * 1.25):
            res = dbm_arrival(v0_km_s, t0, wc, gamma, r0_rs, target_rs)
            if res is not None:
                arrivals.append(res["arrival_time"])
    return {
        **nominal,
        "arrival_earliest": min(arrivals),
        "arrival_latest": max(arrivals),
    }


def is_geoeffective(
    longitude: Optional[float],
    latitude: Optional[float],
    half_angle: Optional[float],
) -> Optional[bool]:
    """Whether the CME cone contains the Sun-Earth line.

    ``longitude``/``latitude`` are the cone-apex direction in Stonyhurst
    heliographic degrees (Earth sits at 0,0); the CME is geoeffective when the
    angular separation of the apex from (0,0) is within ``half_angle``. Returns
    ``None`` when direction or width is missing so the caller can fall back to
    DONKI's own Earth-directed flag.
    """
    if longitude is None or latitude is None or half_angle is None or half_angle <= 0:
        return None
    lon = math.radians(longitude)
    lat = math.radians(latitude)
    # Central angle between the apex direction and (lat=0, lon=0).
    sep = math.degrees(math.acos(max(-1.0, min(1.0, math.cos(lat) * math.cos(lon)))))
    return sep <= half_angle
