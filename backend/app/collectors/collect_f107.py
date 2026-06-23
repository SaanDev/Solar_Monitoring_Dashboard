"""Fetch the F10.7 cm solar radio flux (sfu) from NOAA SWPC.

The 10.7 cm (2800 MHz) radio flux is a daily index of solar activity, measured in
solar flux units (sfu). NOAA publishes the last 30 days of daily values:
  {noaa_base_url}/products/10cm-flux-30-day.json

Each row is ``{"time_tag": "YYYY-MM-DDTHH:MM:SS", "flux": <int>}`` (the timestamp
is naive UTC at the daily observation time).
"""
from datetime import datetime, timezone

import httpx

from app.config import settings


async def fetch_f107_30day_json() -> list[dict]:
    url = f"{settings.noaa_base_url}/products/10cm-flux-30-day.json"
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(url)
        r.raise_for_status()
        return r.json()


def parse_f107(raw: list[dict]) -> list[dict]:
    """Parse the 30-day feed into [{time, flux}], oldest first, dropping bad rows."""
    out: list[dict] = []
    for row in raw:
        try:
            ts = datetime.fromisoformat(row["time_tag"].replace("Z", "+00:00"))
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            flux = float(row["flux"])
        except (KeyError, TypeError, ValueError):
            continue
        out.append({"time": ts, "flux": flux})
    return sorted(out, key=lambda d: d["time"])
