"""Fetch GOES integral proton flux from NOAA SWPC.

Mirrors the NOAA "GOES Proton Flux" product:
https://www.swpc.noaa.gov/products/goes-proton-flux
Source feed (primary GOES satellite, integral protons):
https://services.swpc.noaa.gov/json/goes/primary/integral-protons-{range}.json
"""
from datetime import datetime
import httpx

from app.config import settings

_RANGE_FILES = {
    "6-hour": "integral-protons-6-hour.json",
    "1-day": "integral-protons-1-day.json",
    "3-day": "integral-protons-3-day.json",
    "7-day": "integral-protons-7-day.json",
}


async def fetch_goes_proton_json(range_key: str = "1-day") -> list[dict]:
    filename = _RANGE_FILES.get(range_key, _RANGE_FILES["1-day"])
    url = f"{settings.noaa_base_url}/json/goes/primary/{filename}"
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(url)
        r.raise_for_status()
        return r.json()


def parse_goes_proton(raw: list[dict]) -> list[dict]:
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


# Exact NOAA energy labels (avoid substring collisions like ">=10" in ">=100 MeV").
_GT10 = ">=10 MeV"
_GT50 = ">=50 MeV"
_GT100 = ">=100 MeV"


def records_from_raw(raw: list[dict]) -> list[dict]:
    """Collapse the per-channel NOAA rows into one record per timestamp. Keys match
    the ``goes_proton`` table. Ascending by time."""
    buckets: dict[datetime, dict] = {}
    for r in parse_goes_proton(raw):
        t = r["time"]
        b = buckets.setdefault(
            t,
            {"time": t, "satellite": None, "flux_gt10": None, "flux_gt50": None, "flux_gt100": None},
        )
        if b["satellite"] is None and r.get("satellite") is not None:
            b["satellite"] = r["satellite"]
        energy = r.get("energy", "")
        if energy == _GT10:
            b["flux_gt10"] = r["flux"]
        elif energy == _GT50:
            b["flux_gt50"] = r["flux"]
        elif energy == _GT100:
            b["flux_gt100"] = r["flux"]
    return sorted(buckets.values(), key=lambda d: d["time"])
