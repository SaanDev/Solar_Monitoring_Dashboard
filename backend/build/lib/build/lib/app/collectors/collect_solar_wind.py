"""Fetch solar-wind speed and IMF from NOAA SWPC feeds.

NOAA publishes single-value "summary" products tailored for dashboards:
  /products/summary/solar-wind-speed.json    -> [{"proton_speed":418,"time_tag":...}]
  /products/summary/solar-wind-mag-field.json-> [{"bt":11,"bz_gsm":6,"time_tag":...}]
Timestamps are UTC (no suffix). Each is a list with a single current reading.

For the time series it publishes the propagated solar wind (L1 measurements
propagated to Earth), a single header-row table with plasma + IMF together at
1-minute cadence over the last 7 days:
  /products/geospace/propagated-solar-wind.json
    -> [["time_tag","speed",...,"bz","bt",...], [row], ...]
The first row is a header; values arrive as strings/numbers (or null for gaps).
(The old pre-windowed /products/solar-wind/{plasma,mag}-{range}.json products
are gone, and /json/rtsw/ only keeps ~24 h, so this is the one feed that still
covers a full week.)
"""
from datetime import datetime, timezone

import httpx

from app.config import settings


async def _fetch_summary(name: str) -> dict | None:
    url = f"{settings.noaa_base_url}/products/summary/{name}"
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.get(url)
        r.raise_for_status()
        data = r.json()
    if isinstance(data, list):
        return data[0] if data else None
    return data if isinstance(data, dict) else None


def _ts(row: dict) -> datetime | None:
    raw = row.get("time_tag")
    if not raw:
        return None
    try:
        return datetime.fromisoformat(str(raw).replace("Z", "")).replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _num(row: dict, key: str) -> float | None:
    v = row.get(key)
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


async def fetch_solar_wind_speed() -> dict | None:
    """{time, speed} for the latest plasma reading, or None if unavailable."""
    row = await _fetch_summary("solar-wind-speed.json")
    if row is None:
        return None
    return {"time": _ts(row), "speed": _num(row, "proton_speed")}


async def fetch_solar_wind_mag() -> dict | None:
    """{time, bz, bt} for the latest IMF reading, or None if unavailable."""
    row = await _fetch_summary("solar-wind-mag-field.json")
    if row is None:
        return None
    return {"time": _ts(row), "bz": _num(row, "bz_gsm"), "bt": _num(row, "bt")}


# ── Time series (propagated solar wind, 7 days @ 1 min) ─────────────────────


async def _fetch_product(path: str) -> list:
    url = f"{settings.noaa_base_url}/products/{path}"
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(url)
        r.raise_for_status()
        data = r.json()
    return data if isinstance(data, list) else []


def parse_series_table(raw: list, wanted: dict[str, str]) -> list[dict]:
    """Parse a NOAA header-row table into ``[{"time": dt, alias: float|None}]``.

    ``wanted`` maps source column names to output keys (e.g. ``{"bz_gsm": "bz"}``).
    Columns are resolved by name from the header row so a NOAA column reorder
    can't silently misattribute values; rows with a bad timestamp are skipped
    and unparsable numbers become ``None`` (a gap, not a dropped point).
    """
    if len(raw) < 2 or not isinstance(raw[0], list):
        return []
    header = raw[0]
    try:
        t_idx = header.index("time_tag")
        cols = {alias: header.index(name) for name, alias in wanted.items()}
    except ValueError:
        return []

    out: list[dict] = []
    for row in raw[1:]:
        if not isinstance(row, list) or len(row) <= t_idx:
            continue
        try:
            t = datetime.fromisoformat(str(row[t_idx])).replace(tzinfo=timezone.utc)
        except (TypeError, ValueError):
            continue
        point: dict = {"time": t}
        for alias, idx in cols.items():
            try:
                point[alias] = float(row[idx]) if idx < len(row) and row[idx] is not None else None
            except (TypeError, ValueError):
                point[alias] = None
        out.append(point)
    return out


async def fetch_solar_wind_series() -> list[dict]:
    """[{time, speed, bt, bz}] over the last 7 days, oldest first.

    speed = bulk speed (km/s); bt / bz = IMF total field and z-component (nT),
    propagated from L1 to Earth. One feed carries all three parameters.
    """
    raw = await _fetch_product("geospace/propagated-solar-wind.json")
    return parse_series_table(raw, {"speed": "speed", "bt": "bt", "bz": "bz"})


async def fetch_coupling_series() -> list[dict]:
    """[{time, speed, density, by, bz}] over the last 7 days, oldest first —
    the inputs of the Newell coupling / predicted-Kp forecast (same feed as
    :func:`fetch_solar_wind_series`, different columns; see
    ``app.processing.kp_prediction``)."""
    raw = await _fetch_product("geospace/propagated-solar-wind.json")
    return parse_series_table(
        raw, {"speed": "speed", "density": "density", "by": "by", "bz": "bz"}
    )
