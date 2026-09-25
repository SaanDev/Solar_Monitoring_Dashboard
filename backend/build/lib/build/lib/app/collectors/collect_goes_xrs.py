"""Fetch GOES XRS 1-minute data from NOAA SWPC.

Mirrors the NOAA "GOES X-ray Flux" product:
https://www.swpc.noaa.gov/products/goes-x-ray-flux
Source feed (primary GOES satellite, 1-minute cadence):
https://services.swpc.noaa.gov/json/goes/primary/xrays-{range}.json
"""
from datetime import datetime
import httpx

from app.config import settings

# NOAA exposes 1-day, 3-day, 6-hour and 7-day windows for the primary satellite.
_RANGE_FILES = {
    "6-hour": "xrays-6-hour.json",
    "1-day": "xrays-1-day.json",
    "3-day": "xrays-3-day.json",
    "7-day": "xrays-7-day.json",
}


async def fetch_goes_xrs_json(range_key: str = "1-day") -> list[dict]:
    filename = _RANGE_FILES.get(range_key, _RANGE_FILES["1-day"])
    url = f"{settings.noaa_base_url}/json/goes/primary/{filename}"
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(url)
        r.raise_for_status()
        return r.json()


def parse_goes_xrs(raw: list[dict]) -> list[dict]:
    out = []
    for row in raw:
        try:
            ts = datetime.fromisoformat(row["time_tag"].replace("Z", "+00:00"))
            energy = row.get("energy", "")
            flux = float(row["flux"]) if row.get("flux") not in (None, "null") else None
            satellite = row.get("satellite")
            out.append({"time": ts, "energy": energy, "flux": flux, "satellite": satellite})
        except (KeyError, ValueError):
            continue
    return out


# NOAA energy labels for the two XRS channels.
_SHORT = "0.05-0.4nm"  # XRS-A (0.5-4 Angstrom)
_LONG = "0.1-0.8nm"    # XRS-B (1-8 Angstrom, used for flare class)


def records_from_raw(raw: list[dict]) -> list[dict]:
    """Collapse the per-energy NOAA rows into one record per timestamp, with the
    two channels as columns. Keys match the ``goes_xrs`` table. Ascending by time.
    """
    buckets: dict[datetime, dict] = {}
    for r in parse_goes_xrs(raw):
        t = r["time"]
        b = buckets.setdefault(
            t, {"time": t, "satellite": None, "short_channel": None, "long_channel": None}
        )
        if b["satellite"] is None and r.get("satellite") is not None:
            b["satellite"] = r["satellite"]
        energy = r.get("energy", "")
        if energy == _SHORT:
            b["short_channel"] = r["flux"]
        elif energy == _LONG:
            b["long_channel"] = r["flux"]
    return sorted(buckets.values(), key=lambda d: d["time"])
