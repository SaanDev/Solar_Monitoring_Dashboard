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


# ── Sunspot-number progression (long-term monthly + recent daily) ────────────
# Backs the dashboard's sunspot-progression chart (a longer history than the
# single-day EISN above).


async def fetch_monthly_indices() -> list[dict]:
    """NOAA observed solar-cycle indices: monthly mean + 13-month smoothed SSN
    (and F10.7), back to 1749."""
    url = f"{settings.noaa_base_url}/json/solar-cycle/observed-solar-cycle-indices.json"
    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        r = await client.get(url)
        r.raise_for_status()
        return r.json()


def parse_monthly_ssn(raw: list[dict]) -> list[dict]:
    """Parse the NOAA indices into [{date, ssn, smoothed_ssn}], oldest first.

    NOAA uses -1.0 as a "no value" sentinel; rows without an observed ssn are
    dropped, and a -1.0 smoothed value (the trailing ~6 months, which the 13-month
    average can't yet cover) becomes ``None``.
    """
    rows: list[dict] = []
    for row in raw:
        tag = row.get("time-tag", "")
        try:
            year_s, month_s = tag.split("-")
            d = date(int(year_s), int(month_s), 1)
            ssn = float(row["ssn"])
        except (ValueError, KeyError):
            continue
        if ssn < 0:
            continue
        smoothed = row.get("smoothed_ssn")
        try:
            smoothed = float(smoothed)
        except (TypeError, ValueError):
            smoothed = None
        rows.append(
            {"date": d, "ssn": ssn, "smoothed_ssn": smoothed if (smoothed or 0) >= 0 else None}
        )
    return sorted(rows, key=lambda r: r["date"])


async def fetch_daily_ssn_csv() -> str:
    """SILSO daily total sunspot number CSV (full record since 1818)."""
    url = f"{settings.silso_base_url}/SILSO/INFO/sndtotcsv.php"
    async with httpx.AsyncClient(timeout=60, follow_redirects=True) as client:
        r = await client.get(url)
        r.raise_for_status()
        return r.text


def parse_daily_ssn(text: str) -> list[dict]:
    """Parse the SILSO daily CSV into [{date, number}], oldest first.

    Semicolon-separated: year;month;day;decimal_date;ssn;ssn_sd;n_obs;flag.
    SILSO uses -1 for days with no value, which are skipped.
    """
    rows: list[dict] = []
    for line in text.splitlines():
        parts = [p.strip() for p in line.split(";")]
        if len(parts) < 5:
            continue
        try:
            d = date(int(parts[0]), int(parts[1]), int(parts[2]))
            number = float(parts[4])
        except (ValueError, IndexError):
            continue
        if number < 0:
            continue
        rows.append({"date": d, "number": number})
    return rows
