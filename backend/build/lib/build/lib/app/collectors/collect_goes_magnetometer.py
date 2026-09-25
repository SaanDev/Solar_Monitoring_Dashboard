"""Fetch GOES magnetometer data from NOAA SWPC.

Mirrors the NOAA "GOES Magnetometer" product. Source feed (primary GOES
satellite, 1-minute cadence):
https://services.swpc.noaa.gov/json/goes/primary/magnetometers-{range}.json

Unlike the per-energy flux feeds, each NOAA row is already one timestamp with the
field components Hp (northward), He (earthward), Hn (eastward) and the total field
magnitude, all in nT.
"""
from datetime import datetime
import httpx

from app.config import settings

_RANGE_FILES = {
    "6-hour": "magnetometers-6-hour.json",
    "1-day": "magnetometers-1-day.json",
    "3-day": "magnetometers-3-day.json",
    "7-day": "magnetometers-7-day.json",
}


async def fetch_goes_magnetometer_json(range_key: str = "1-day") -> list[dict]:
    filename = _RANGE_FILES.get(range_key, _RANGE_FILES["1-day"])
    url = f"{settings.noaa_base_url}/json/goes/primary/{filename}"
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(url)
        r.raise_for_status()
        return r.json()


def _num(value) -> float | None:
    try:
        return float(value) if value not in (None, "null") else None
    except (TypeError, ValueError):
        return None


def records_from_raw(raw: list[dict]) -> list[dict]:
    """Normalize NOAA magnetometer rows to the ``goes_magnetometer`` table keys,
    ascending by time. One row per timestamp already, so no collapsing needed.
    """
    out: list[dict] = []
    for row in raw:
        try:
            ts = datetime.fromisoformat(row["time_tag"].replace("Z", "+00:00"))
        except (KeyError, ValueError):
            continue
        out.append(
            {
                "time": ts,
                "satellite": row.get("satellite"),
                "hp": _num(row.get("Hp")),
                "he": _num(row.get("He")),
                "hn": _num(row.get("Hn")),
                "total": _num(row.get("total")),
            }
        )
    return sorted(out, key=lambda d: d["time"])
