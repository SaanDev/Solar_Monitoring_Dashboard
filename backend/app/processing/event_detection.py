"""Threshold-crossing event detection over numeric space-weather time-series.

Pure functions (no DB, no I/O) so detection is unit-testable. Each detector turns
a list of time-ordered samples into discrete event dicts: a contiguous span where
the measured quantity stays past a NOAA/scientific threshold becomes one event,
carrying its peak and a human-readable severity label.

Short gaps — a missing sample or a brief dip below threshold — within ``MAX_GAP``
are bridged so a single dropout doesn't fragment one flare/storm into several
events. A span that runs to the most recent sample is reported as *ongoing*
(``end_time=None``).

Reuses the existing classification helpers so the scales stay defined in one place:
``flare_class`` (X-ray A/B/C/M/X), ``storm_scale`` (proton S-scale),
``kp_storm_scale`` (geomagnetic G-scale), ``dst_storm_level`` (Dst intensity).
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Callable, Optional

from app.processing.flare_class import flare_class
from app.processing.geomag_scale import dst_storm_level, kp_storm_scale
from app.processing.storm_scale import storm_scale

# Bridge sub-threshold gaps up to this long so one event isn't split by a single
# missing/dipping sample. The tolerance must track each feed's cadence: GOES
# XRS/proton arrive every ~1-5 min, while Kp is 3-hourly and Dst hourly — so a
# 20-min gap that means "two flares" would wrongly split one multi-hour storm.
FLARE_MAX_GAP = timedelta(minutes=20)
PROTON_MAX_GAP = timedelta(minutes=30)
KP_MAX_GAP = timedelta(hours=6)
DST_MAX_GAP = timedelta(hours=3)

# Detection thresholds (onset of the lowest NOAA/scientific class for each).
FLARE_MIN_FLUX = 1e-6   # >= C1.0 GOES long-channel flux (W/m^2); below this is quiet.
PROTON_MIN_PFU = 10.0   # NOAA SEP / S1 onset (>=10 MeV >= 10 pfu).
KP_MIN_STORM = 5.0      # NOAA G1 onset (confirmed geomagnetic storm).
DST_MAX_NT = -50.0      # moderate-storm onset (Dst <= -50 nT).

# X-ray flares are NOT a fixed-threshold crossing (unlike proton/Kp/Dst). Near
# solar maximum the GOES long-channel *background* rides up to C-level, so
# "flux >= C1" stays true for hours-to-days — a big M/X flare's slow decay never
# dips back under the threshold, so its span runs to the latest sample and reads
# as perpetually "in progress", and every flare on that elevated background merges
# into one span whose peak is meaningless. Instead flares are segmented the way
# NOAA/SWPC defines an X-ray event: an onset is a genuine *brightening* over the
# local background, and the flare *ends* once it decays half-way from its peak
# back to that background — not when it finally slips under C1.
FLARE_RISE_WINDOW = timedelta(minutes=10)  # trailing window for the pre-flare background.
FLARE_RISE_FACTOR = 1.4    # onset: flux must exceed 1.4x the local background AND be rising.
FLARE_END_FRACTION = 0.5   # end: flux decays half-way from peak back to background.

# "Possible geomagnetic storm" (watch) onsets: elevated, pre-storm activity that
# may develop into a storm. A geomagnetic span is now flagged from these lower
# thresholds; whether it is reported as a *possible* storm or a confirmed one is
# decided by the peak value reached (see detect_kp_storms / detect_dst_storms).
KP_WATCH_MIN = 4.0      # active conditions (Kp 4) — below the G1 storm onset.
DST_WATCH_MAX = -30.0   # weak disturbance (Dst <= -30 nT) — above moderate-storm onset.

# Severity label for the pre-storm "possible storm" band.
POSSIBLE_STORM = "Possible storm"

Sample = tuple[datetime, Optional[float]]


def _spans(
    samples: list[Sample],
    is_active: Callable[[float], bool],
    max_gap: timedelta,
    peak_is_min: bool = False,
) -> list[dict]:
    """Group time-ordered samples into spans where ``is_active`` holds.

    Active samples no more than ``max_gap`` apart belong to the same span.
    ``peak_is_min`` selects the extremum that counts as the peak (max for flux/Kp,
    min for Dst). A span whose last active sample is the most recent sample overall
    is treated as ongoing (``end_time=None``).
    """
    pts = sorted((t, v) for t, v in samples if v is not None)
    if not pts:
        return []
    last_time = pts[-1][0]

    spans: list[dict] = []
    cur: Optional[dict] = None
    for t, v in pts:
        if not is_active(v):
            continue
        if cur is not None and t - cur["last_active"] <= max_gap:
            cur["last_active"] = t
            better = v < cur["peak_value"] if peak_is_min else v > cur["peak_value"]
            if better:
                cur["peak_value"] = v
                cur["peak_time"] = t
        else:
            if cur is not None:
                spans.append(cur)
            cur = {"start_time": t, "last_active": t, "peak_time": t, "peak_value": v}
    if cur is not None:
        spans.append(cur)

    return [
        {
            "start_time": s["start_time"],
            "end_time": None if s["last_active"] == last_time else s["last_active"],
            "peak_time": s["peak_time"],
            "peak_value": s["peak_value"],
        }
        for s in spans
    ]


_FLARE_URL = "https://www.swpc.noaa.gov/products/goes-x-ray-flux"
_PROTON_URL = "https://www.swpc.noaa.gov/products/goes-proton-flux"
_KP_URL = "https://www.swpc.noaa.gov/products/planetary-k-index"
_DST_URL = "https://wdc.kugi.kyoto-u.ac.jp/dstdir/"


def _flare_spans(samples: list[Sample]) -> list[dict]:
    """Segment GOES long-channel flux into individual flares (NOAA/SWPC-style).

    Unlike the fixed-threshold ``_spans``, a flare is *onset* only when the flux
    rises meaningfully above the recent background (>= ``FLARE_RISE_FACTOR`` x the
    trailing-window minimum, while above the C1 floor, and while actually
    increasing), and is *closed* once it decays half-way from its peak back to
    that onset background. This keeps a slowly-decaying M/X flare from lingering
    as an endless "in progress" span, stops an elevated background from reading as
    one giant flare, and separates distinct flares that share that background. A
    flare still elevated at the most recent sample is ongoing (``end_time=None``).
    """
    pts = sorted((t, v) for t, v in samples if v is not None and v > 0)
    if not pts:
        return []
    last_time = pts[-1][0]

    out: list[dict] = []
    window: list[Sample] = []          # (t, flux) within the trailing FLARE_RISE_WINDOW
    cur: Optional[dict] = None
    prev_t: Optional[datetime] = None
    prev_v = 0.0

    def _open(t: datetime, v: float, bg: float) -> dict:
        return {"start_time": t, "background": bg, "peak_time": t, "peak_value": v, "last_active": t}

    def _emit(fl: dict, end_time: Optional[datetime]) -> None:
        out.append({
            "start_time": fl["start_time"],
            "end_time": end_time,
            "peak_time": fl["peak_time"],
            "peak_value": fl["peak_value"],
        })

    for t, v in pts:
        while window and t - window[0][0] > FLARE_RISE_WINDOW:
            window.pop(0)
        background = min(f for _, f in window) if window else None
        rising = prev_t is not None and (t - prev_t) <= FLARE_RISE_WINDOW and v > prev_v
        onset = (
            background is not None
            and v >= FLARE_MIN_FLUX
            and v >= background * FLARE_RISE_FACTOR
            and rising
        )

        if cur is None:
            if onset:
                cur = _open(t, v, background)
        elif t - cur["last_active"] > FLARE_MAX_GAP:
            _emit(cur, cur["last_active"])          # data dropout: end before the gap
            cur = _open(t, v, background) if onset else None
        else:
            if v > cur["peak_value"]:
                cur["peak_value"], cur["peak_time"] = v, t
            end_level = cur["background"] + FLARE_END_FRACTION * (cur["peak_value"] - cur["background"])
            if v <= end_level:
                _emit(cur, t)                        # decayed past the half-way point
                cur = None
            else:
                cur["last_active"] = t

        window.append((t, v))
        prev_t, prev_v = t, v

    if cur is not None:
        _emit(cur, None if cur["last_active"] == last_time else cur["last_active"])

    return out


def detect_xray_flares(points: list[dict]) -> list[dict]:
    samples = [(p["time"], p.get("long_channel")) for p in points]
    out = []
    for s in _flare_spans(samples):
        cls = flare_class(s["peak_value"])
        out.append({
            "type": "xray_flare",
            "severity": cls,
            "description": (
                f"{cls} X-ray flare - GOES long-channel peak "
                f"{s['peak_value']:.1e} W/m^2"
            ),
            "source_url": _FLARE_URL,
            **s,
        })
    return out


def detect_proton_events(points: list[dict]) -> list[dict]:
    samples = [(p["time"], p.get("flux_gt10")) for p in points]
    out = []
    for s in _spans(samples, lambda v: v >= PROTON_MIN_PFU, PROTON_MAX_GAP):
        scale = storm_scale(s["peak_value"])
        out.append({
            "type": "proton_event",
            "severity": scale,
            "description": (
                f"Solar radiation storm {scale} - >=10 MeV proton flux peak "
                f"{s['peak_value']:.1f} pfu"
            ),
            "source_url": _PROTON_URL,
            **s,
        })
    return out


def detect_kp_storms(points: list[dict]) -> list[dict]:
    """Geomagnetic activity from Kp. Spans are flagged from the watch onset
    (Kp >= KP_WATCH_MIN); a span whose peak reaches the G1 onset is a confirmed
    storm (G-scale), otherwise it is a *possible* storm (active conditions)."""
    samples = [(p["time"], p.get("kp")) for p in points]
    out = []
    for s in _spans(samples, lambda v: v >= KP_WATCH_MIN, KP_MAX_GAP):
        scale = kp_storm_scale(s["peak_value"])  # None when peak < KP_MIN_STORM
        if scale:
            severity = scale
            description = f"Geomagnetic storm {scale} - Kp peaked at {s['peak_value']:.1f}"
        else:
            severity = POSSIBLE_STORM
            description = (
                "Possible geomagnetic storm - Kp peaked at "
                f"{s['peak_value']:.1f} (active conditions)"
            )
        out.append({
            "type": "geomagnetic_storm_kp",
            "severity": severity,
            "description": description,
            "source_url": _KP_URL,
            **s,
        })
    return out


def detect_dst_storms(points: list[dict]) -> list[dict]:
    """Geomagnetic activity from Dst. Spans are flagged from the watch onset
    (Dst <= DST_WATCH_MAX); a span whose minimum reaches the moderate-storm onset
    is a confirmed storm (Dst intensity level), otherwise a *possible* storm."""
    samples = [(p["time"], p.get("dst")) for p in points]
    out = []
    for s in _spans(samples, lambda v: v <= DST_WATCH_MAX, DST_MAX_GAP, peak_is_min=True):
        if s["peak_value"] <= DST_MAX_NT:
            severity = dst_storm_level(s["peak_value"])  # Moderate / Intense / Super
            description = f"{severity} - Dst minimum {s['peak_value']:.0f} nT"
        else:
            severity = POSSIBLE_STORM
            description = (
                "Possible geomagnetic storm - Dst dropped to "
                f"{s['peak_value']:.0f} nT (weak disturbance)"
            )
        out.append({
            "type": "geomagnetic_storm_dst",
            "severity": severity,
            "description": description,
            "source_url": _DST_URL,
            **s,
        })
    return out


def detect_events(
    xrs: list[dict],
    proton: list[dict],
    kp: list[dict],
    dst: list[dict],
) -> list[dict]:
    """Run every detector and return all events, newest first."""
    events = (
        detect_xray_flares(xrs)
        + detect_proton_events(proton)
        + detect_kp_storms(kp)
        + detect_dst_storms(dst)
    )
    events.sort(key=lambda e: e["start_time"], reverse=True)
    return events
