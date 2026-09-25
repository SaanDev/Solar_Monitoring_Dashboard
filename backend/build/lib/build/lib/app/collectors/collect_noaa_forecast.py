"""Fetch NOAA SWPC forecast products: 3-day R/S/G outlook + OVATION aurora power.

noaa-scales.json keys days by offset relative to the issue time:
  "-1" = yesterday (observed maxima), "0" = today so far (observed),
  "1".."3" = the 3-day forecast. Observed days carry reached Scale levels;
  forecast days carry the predicted G level plus R/S *probabilities* (strings,
  e.g. "70"). aurora-nowcast-hemi-power.txt is a '#'-commented table of
  ``observation forecast north_gw south_gw`` rows at 5-minute cadence.
"""
from datetime import datetime, timezone

import httpx

from app.config import settings


def _int(v) -> int | None:
    try:
        return int(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def _day(d: dict) -> dict:
    """One noaa-scales.json day entry -> a flat scale-day record."""
    r = d.get("R") or {}
    s = d.get("S") or {}
    g = d.get("G") or {}
    return {
        "date": d.get("DateStamp"),
        "r_scale": r.get("Scale"),
        "r_text": r.get("Text"),
        "r_minor_prob": _int(r.get("MinorProb")),
        "r_major_prob": _int(r.get("MajorProb")),
        "s_scale": s.get("Scale"),
        "s_text": s.get("Text"),
        "s_prob": _int(s.get("Prob")),
        "g_scale": g.get("Scale"),
        "g_text": g.get("Text"),
    }


def parse_noaa_scales(raw: dict) -> dict:
    """-> ``{issued, observed, current, forecast: [day1..day3]}``.

    Missing/malformed day keys are skipped; ``issued`` comes from the current
    day's Date/TimeStamp (the product's issue time).
    """
    if not isinstance(raw, dict):
        return {"issued": None, "observed": None, "current": None, "forecast": []}
    current = raw.get("0") if isinstance(raw.get("0"), dict) else None
    observed = raw.get("-1") if isinstance(raw.get("-1"), dict) else None
    forecast = [
        _day(raw[k]) for k in ("1", "2", "3") if isinstance(raw.get(k), dict)
    ]
    issued = None
    if current and current.get("DateStamp") and current.get("TimeStamp"):
        try:
            issued = datetime.fromisoformat(
                f"{current['DateStamp']}T{current['TimeStamp']}"
            ).replace(tzinfo=timezone.utc)
        except ValueError:
            issued = None
    return {
        "issued": issued,
        "observed": _day(observed) if observed else None,
        "current": _day(current) if current else None,
        "forecast": forecast,
    }


async def fetch_noaa_scales() -> dict:
    url = f"{settings.noaa_base_url}/products/noaa-scales.json"
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.get(url)
        r.raise_for_status()
        return parse_noaa_scales(r.json())


# ── OVATION hemispheric power ────────────────────────────────────────────────


def _hemi_dt(raw: str) -> datetime | None:
    try:
        return datetime.strptime(raw, "%Y-%m-%d_%H:%M").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def parse_hemi_power(text: str) -> dict | None:
    """The most recent row of the hemispheric-power table, or ``None``."""
    for line in reversed(text.splitlines()):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) < 4:
            continue
        obs, fc = _hemi_dt(parts[0]), _hemi_dt(parts[1])
        try:
            north, south = float(parts[2]), float(parts[3])
        except ValueError:
            continue
        if obs is None:
            continue
        return {
            "observation_time": obs,
            "forecast_time": fc,
            "north_gw": north,
            "south_gw": south,
        }
    return None


async def fetch_hemi_power() -> dict | None:
    url = f"{settings.noaa_base_url}/text/aurora-nowcast-hemi-power.txt"
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.get(url)
        r.raise_for_status()
        return parse_hemi_power(r.text)
