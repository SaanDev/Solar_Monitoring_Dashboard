"""Fetch the planetary Kp index from NOAA SWPC.

Mirrors the NOAA "Planetary K-index" product:
https://www.swpc.noaa.gov/products/planetary-k-index
Source feed (3-hourly Kp, ~7 days):
https://services.swpc.noaa.gov/products/noaa-planetary-k-index.json

NOTE: this feed is a JSON array of objects with keys
{time_tag, Kp, a_running, station_count}. Timestamps are UTC (no suffix).
"""
from datetime import datetime, timezone
import httpx

from app.config import settings


async def fetch_kp_json() -> list[dict]:
    url = f"{settings.noaa_base_url}/products/noaa-planetary-k-index.json"
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(url)
        r.raise_for_status()
        return r.json()


def parse_kp(raw: list[dict]) -> list[dict]:
    out = []
    for row in raw:
        try:
            ts = datetime.fromisoformat(row["time_tag"].replace("Z", "")).replace(
                tzinfo=timezone.utc
            )
            kp = float(row["Kp"])
            out.append({"time": ts, "kp": kp})
        except (KeyError, ValueError, TypeError):
            continue
    return out


# ─── Historical Kp from GFZ Potsdam (full record since 1932) ─────────────────
# JSON service: /app/json/?start=...&end=...&index=Kp
# -> {"datetime": [ISO...], "Kp": [float...], "status": [...]}, interval-start times.


def parse_kp_gfz(data: dict) -> list[dict]:
    out: list[dict] = []
    for dt, kp in zip(data.get("datetime", []), data.get("Kp", [])):
        try:
            ts = datetime.fromisoformat(str(dt).replace("Z", "+00:00"))
            out.append({"time": ts, "kp": float(kp)})
        except (ValueError, TypeError):
            continue
    return out


async def fetch_kp_gfz(start: datetime, end: datetime) -> list[dict]:
    """Historical Kp records ({time, kp}) from GFZ for an arbitrary date range."""
    params = {
        "start": start.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "end": end.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "index": "Kp",
    }
    url = f"{settings.gfz_base_url}/app/json/"
    async with httpx.AsyncClient(timeout=40, follow_redirects=True) as client:
        r = await client.get(url, params=params)
        r.raise_for_status()
        return parse_kp_gfz(r.json())
