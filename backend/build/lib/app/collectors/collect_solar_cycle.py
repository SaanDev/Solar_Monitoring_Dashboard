"""Fetch NOAA's monthly solar-cycle indices: observed + Cycle 25 prediction.

Two JSON products under /json/solar-cycle/:
  observed-solar-cycle-indices.json  — monthly SSN (SILSO) + smoothed SSN +
                                       F10.7 + smoothed F10.7 back to 1749.
  predicted-solar-cycle.json         — the official NOAA/NASA Cycle 25 panel
                                       prediction: monthly SSN and F10.7 with
                                       high/low uncertainty bounds.
Months are "YYYY-MM" strings under the "time-tag" key; missing values are the
sentinel -1.0 (mapped to None here). ``smoothed_ssn`` trails ~6 months (the
13-month smoothing window must complete before a value is published).
"""
import httpx

from app.config import settings


def _val(row: dict, key: str) -> float | None:
    """A feed value, mapping the -1.0 missing-data sentinel (and junk) to None."""
    v = row.get(key)
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if f < 0 else f


def parse_observed(raw: list, since: str) -> list[dict]:
    """Monthly observed rows from ``since`` ("YYYY-MM"), oldest first."""
    out = []
    for row in raw if isinstance(raw, list) else []:
        if not isinstance(row, dict):
            continue
        month = str(row.get("time-tag") or "")
        if len(month) != 7 or month < since:
            continue
        out.append(
            {
                "month": month,
                "ssn": _val(row, "ssn"),
                "smoothed_ssn": _val(row, "smoothed_ssn"),
                "f107": _val(row, "f10.7"),
                "smoothed_f107": _val(row, "smoothed_f10.7"),
            }
        )
    out.sort(key=lambda r: r["month"])
    return out


def parse_predicted(raw: list) -> list[dict]:
    """Monthly prediction rows with uncertainty bounds, oldest first."""
    out = []
    for row in raw if isinstance(raw, list) else []:
        if not isinstance(row, dict):
            continue
        month = str(row.get("time-tag") or "")
        if len(month) != 7:
            continue
        out.append(
            {
                "month": month,
                "ssn": _val(row, "predicted_ssn"),
                "ssn_high": _val(row, "high_ssn"),
                "ssn_low": _val(row, "low_ssn"),
                "f107": _val(row, "predicted_f10.7"),
                "f107_high": _val(row, "high_f10.7"),
                "f107_low": _val(row, "low_f10.7"),
            }
        )
    out.sort(key=lambda r: r["month"])
    return out


async def _fetch_json(name: str) -> list:
    url = f"{settings.noaa_base_url}/json/solar-cycle/{name}"
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(url)
        r.raise_for_status()
        data = r.json()
    return data if isinstance(data, list) else []


async def fetch_observed(since: str) -> list[dict]:
    return parse_observed(await _fetch_json("observed-solar-cycle-indices.json"), since)


async def fetch_predicted() -> list[dict]:
    return parse_predicted(await _fetch_json("predicted-solar-cycle.json"))
