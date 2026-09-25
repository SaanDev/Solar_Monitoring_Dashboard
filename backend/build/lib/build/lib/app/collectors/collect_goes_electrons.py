"""Fetch GOES integral electron flux from NOAA SWPC.

Mirrors the NOAA "GOES Electron Flux" product. Source feed (primary GOES
satellite, 5-minute cadence):
https://services.swpc.noaa.gov/json/goes/primary/integral-electrons-{range}.json

The primary feed exposes a single integral channel, >=2 MeV (the relativistic
electron flux used for internal-charging risk).
"""
from datetime import datetime
import httpx

from app.config import settings

# NOAA exposes 1-day, 3-day, 6-hour and 7-day windows for the primary satellite.
_RANGE_FILES = {
    "6-hour": "integral-electrons-6-hour.json",
    "1-day": "integral-electrons-1-day.json",
    "3-day": "integral-electrons-3-day.json",
    "7-day": "integral-electrons-7-day.json",
}

# NOAA energy label for the integral electron channel.
_GE2 = ">=2 MeV"


async def fetch_goes_electrons_json(range_key: str = "1-day") -> list[dict]:
    filename = _RANGE_FILES.get(range_key, _RANGE_FILES["1-day"])
    url = f"{settings.noaa_base_url}/json/goes/primary/{filename}"
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(url)
        r.raise_for_status()
        return r.json()


def records_from_raw(raw: list[dict]) -> list[dict]:
    """Collapse the per-energy NOAA rows into one record per timestamp. Keys match
    the ``goes_electron`` table. Ascending by time.
    """
    buckets: dict[datetime, dict] = {}
    for row in raw:
        try:
            ts = datetime.fromisoformat(row["time_tag"].replace("Z", "+00:00"))
        except (KeyError, ValueError):
            continue
        if row.get("energy") != _GE2:
            continue
        flux = row.get("flux")
        try:
            flux = float(flux) if flux not in (None, "null") else None
        except (TypeError, ValueError):
            flux = None
        b = buckets.setdefault(ts, {"time": ts, "satellite": None, "flux_ge2mev": None})
        if b["satellite"] is None and row.get("satellite") is not None:
            b["satellite"] = row["satellite"]
        b["flux_ge2mev"] = flux
    return sorted(buckets.values(), key=lambda d: d["time"])
