"""Interactive measurements + region light curves for the Data Analysis feature.

Thin session/WCS glue over the ported pure-math modules:

* ``app.services.solar.image_measure`` — ruler / line profile / region stats.
* ``app.services.solar.solar_data_analysis.extract_region_lightcurve`` — ROI
  intensity vs time (DN/s-normalised) + ``radio_euv_lag`` for timing an EUV
  brightening against an e-CALLISTO radio-burst onset.

All inputs arrive as **data-pixel coordinates** (0-based, origin bottom-left —
the interactive canvas convention); conversions to helioprojective arcsec go
through the frame's WCS so the numbers match the desktop tool exactly.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from app.services import aia_data_service as data


def _arcsec(m: Any, px: float, py: float) -> tuple[float, float]:
    import astropy.units as u

    coord = m.wcs.pixel_to_world(float(px), float(py))
    return float(coord.Tx.to_value(u.arcsec)), float(coord.Ty.to_value(u.arcsec))


def _rsun_arcsec(m: Any) -> float | None:
    import astropy.units as u

    try:
        return float(m.rsun_obs.to_value(u.arcsec))
    except Exception:
        return None


def measure_ruler(session_id: str, frame: int, x1: float, y1: float, x2: float, y2: float) -> dict:
    """Two-point plane-of-sky distance (arcsec / R☉ / km) + position angle."""
    from app.services.solar.image_measure import ruler_measurement

    m = data.load_map(session_id, frame)
    p0 = _arcsec(m, x1, y1)
    p1 = _arcsec(m, x2, y2)
    r = ruler_measurement(p0, p1, rsun_arcsec=_rsun_arcsec(m))
    return {
        "p0_arcsec": list(p0),
        "p1_arcsec": list(p1),
        "dx_arcsec": r.dx_arcsec,
        "dy_arcsec": r.dy_arcsec,
        "distance_arcsec": r.distance_arcsec,
        "distance_rsun": r.distance_rsun,
        "distance_km": r.distance_km,
        "position_angle_deg": r.position_angle_deg,
    }


def measure_profile(
    session_id: str, frame: int, x1: float, y1: float, x2: float, y2: float
) -> dict:
    """Intensity along an arbitrary segment, with an arcsec distance scale."""
    import math

    import numpy as np

    from app.services.solar.image_measure import line_profile, ruler_measurement

    m = data.load_map(session_id, frame)
    dist_px, values = line_profile(np.asarray(m.data, dtype=float), (x1, y1), (x2, y2))
    # Angular scale along this segment: total arcsec length / total pixel length.
    ruler = ruler_measurement(_arcsec(m, x1, y1), _arcsec(m, x2, y2), rsun_arcsec=_rsun_arcsec(m))
    length_px = math.hypot(x2 - x1, y2 - y1) or 1.0
    scale = ruler.distance_arcsec / length_px
    values = np.asarray(values, dtype=float)
    return {
        "distance_arcsec": [float(d * scale) for d in dist_px],
        "values": [None if not np.isfinite(v) else float(v) for v in values],
        "n": int(values.size),
        "length_arcsec": ruler.distance_arcsec,
        "length_rsun": ruler.distance_rsun,
    }


def measure_region(
    session_id: str, frame: int, x0: float, y0: float, x1: float, y1: float
) -> dict:
    """Rectangle statistics + intensity-weighted centroid (px and arcsec)."""
    import numpy as np

    from app.services.solar.image_measure import region_stats

    m = data.load_map(session_id, frame)
    xa, xb = sorted((int(round(x0)), int(round(x1))))
    ya, yb = sorted((int(round(y0)), int(round(y1))))
    stats = region_stats(np.asarray(m.data, dtype=float), (xa, xb, ya, yb))
    ctx, cty = _arcsec(m, stats.centroid_x_pix, stats.centroid_y_pix)
    return {
        "n_pixels": stats.n_pixels,
        "min": stats.min,
        "max": stats.max,
        "mean": stats.mean,
        "median": stats.median,
        "std": stats.std,
        "centroid_x_pix": stats.centroid_x_pix,
        "centroid_y_pix": stats.centroid_y_pix,
        "centroid_tx_arcsec": ctx,
        "centroid_ty_arcsec": cty,
    }


def height_time(session_id: str, picks: list[Any]) -> dict:
    """CME height–time fit from leading-edge picks (plane-of-sky).

    Each pick's radial height comes from the frame's WCS (helioprojective
    arcsec from disk centre → R☉ via ``RSUN_OBS``) — equivalent to the desktop
    ``pixel_radius_to_rsun`` path but exact under roll/rotation. A linear fit
    gives the mean speed (km/s); with ≥3 picks the quadratic fit adds the
    constant acceleration (km/s²), plus per-segment instantaneous speeds.
    """
    import math

    from app.services.solar.coronagraph import RSUN_KM, fit_height_time

    session = data.get_session(session_id)
    times_by_index = {fr.index: fr.time for fr in session.frames}

    points: list[dict] = []
    for p in picks:
        frame = int(p.frame)
        t = times_by_index.get(frame)
        m = data.load_map(session_id, frame)
        tx, ty = _arcsec(m, p.px, p.py)
        rsun = _rsun_arcsec(m) or 960.0
        r_rsun = math.hypot(tx, ty) / rsun
        points.append(
            {
                "frame": frame,
                "time": t.isoformat() if t else None,
                "px": float(p.px),
                "py": float(p.py),
                "r_rsun": r_rsun,
                "height_km": r_rsun * RSUN_KM,
                "_t": t.replace(tzinfo=None) if (t and t.tzinfo) else t,
            }
        )

    timed = [pt for pt in points if pt["_t"] is not None]
    fit_out: dict = {}
    if len(timed) >= 2:
        fit = fit_height_time([pt["_t"] for pt in timed], [pt["height_km"] for pt in timed])
        seg = [None if s != s else float(s) for s in fit.segment_speeds_km_s]
        fit_out = {
            "speed_km_s": fit.speed_km_s,
            "acceleration_km_s2": None
            if fit.acceleration_km_s2 != fit.acceleration_km_s2
            else fit.acceleration_km_s2,  # NaN → None (< 3 picks)
            "segment_speeds_km_s": seg,
        }

    for pt in points:
        pt.pop("_t", None)
    return {"points": points, "n": len(points), **fit_out}


def region_lightcurve(
    session_id: str,
    x0: float,
    y0: float,
    x1: float,
    y1: float,
    statistic: str = "mean",
    radio_start: datetime | None = None,
    radio_end: datetime | None = None,
) -> dict:
    """ROI intensity vs time across every frame of a session.

    Frames are DN/s-normalised (exposure-time divided) so the curve is physical.
    With a radio-burst window supplied, the EUV-peak-minus-radio-onset lag is
    reported (positive = EUV peak follows the radio onset) — the e-CALLISTO ↔
    imaging timing link the desktop tool provides.
    """
    from app.services.solar.solar_data_analysis import (
        extract_region_lightcurve,
        radio_euv_lag,
    )

    session = data.get_session(session_id)
    frames = [data.load_map(session_id, fr.index) for fr in session.frames]

    xa, xb = sorted((int(round(x0)), int(round(x1))))
    ya, yb = sorted((int(round(y0)), int(round(y1))))
    lc = extract_region_lightcurve(frames, (xa, xb, ya, yb), statistic=statistic)

    peak_idx = lc.peak_index()
    peak_time = lc.times[peak_idx] if 0 <= peak_idx < len(lc.times) else None
    naive_start = radio_start.replace(tzinfo=None) if radio_start and radio_start.tzinfo else radio_start
    naive_peak = peak_time.replace(tzinfo=None) if peak_time and peak_time.tzinfo else peak_time
    lag = radio_euv_lag(naive_start, naive_peak)

    return {
        "times": [t.isoformat() if t else None for t in lc.times],
        "values": [None if v != v else float(v) for v in lc.values],  # NaN → None
        "unit": lc.unit,
        "statistic": lc.statistic,
        "bounds": [xa, xb, ya, yb],
        "peak_index": peak_idx,
        "peak_time": peak_time.isoformat() if peak_time else None,
        "radio_start": radio_start.isoformat() if radio_start else None,
        "radio_end": radio_end.isoformat() if radio_end else None,
        "radio_euv_lag_s": lag,
    }
