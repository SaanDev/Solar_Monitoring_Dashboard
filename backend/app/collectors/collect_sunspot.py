"""Fetch the current daily Estimated International Sunspot Number (EISN) from SILSO.

SILSO (SIDC, Royal Observatory of Belgium) publishes a running CSV of the current
month's daily EISN:
  {silso_base_url}/SILSO/DATA/EISN/EISN_current.csv

Each comma-separated row is:
  year, month, day, decimal_date, EISN, EISN_sd, n_calc_stations, n_avail_stations

The EISN is a provisional same-day estimate; early in the UTC day it rests on very
few stations, so the latest *settled* day (a meaningful station count) is preferred
over a jumpy single-station current-day value.
"""
from datetime import date

import httpx

from app.config import settings

# Minimum contributing stations for a daily EISN to be treated as settled.
_MIN_STATIONS = 3


async def fetch_eisn_csv() -> str:
    url = f"{settings.silso_base_url}/SILSO/DATA/EISN/EISN_current.csv"
    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        r = await client.get(url)
        r.raise_for_status()
        return r.text


def parse_eisn(text: str) -> list[dict]:
    """Parse the EISN CSV into [{date, number, n_calc}], oldest first."""
    rows: list[dict] = []
    for line in text.splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 7:
            continue
        try:
            d = date(int(parts[0]), int(parts[1]), int(parts[2]))
            number = float(parts[4])
            n_calc = int(float(parts[6]))
        except (ValueError, IndexError):
            continue
        if number < 0:  # SILSO uses negatives for "no value"
            continue
        rows.append({"date": d, "number": number, "n_calc": n_calc})
    return rows


def latest_eisn(rows: list[dict]) -> dict | None:
    """Most recent settled day, falling back to the latest available row."""
    if not rows:
        return None
    settled = [r for r in rows if r["n_calc"] >= _MIN_STATIONS]
    return (settled or rows)[-1]
