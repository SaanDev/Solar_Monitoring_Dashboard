"""Fetch CMEs (with WSA-ENLIL arrival predictions) from NASA DONKI.

DONKI (Space Weather Database Of Notifications, Knowledge, Information) has a
public web service at kauai.ccmc.gsfc.nasa.gov that needs no API key:
  /WS/get/CME?startDate=YYYY-MM-DD&endDate=YYYY-MM-DD

Each CME carries analyst measurements (``cmeAnalyses``; the one flagged
``isMostAccurate`` is the operative cone-model fit) and each analysis a list of
WSA-ENLIL model runs (``enlilList``). A run's ``estimatedShockArrivalTime`` —
when present — is the predicted Earth arrival; ``kp_90``/``kp_135``/``kp_180``
are its predicted Kp for different IMF clock angles. Analyses are revised for
days after an eruption, so records must be upserted by ``activityID``.
Timestamps are minute-resolution UTC ("2026-06-24T13:00Z").
"""
from datetime import date, datetime, timezone

import httpx

from app.config import settings


def _dt(raw) -> datetime | None:
    if not raw:
        return None
    try:
        return datetime.fromisoformat(str(raw).replace("Z", "")).replace(
            tzinfo=timezone.utc
        )
    except ValueError:
        return None


def _num(v) -> float | None:
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def pick_analysis(analyses: list | None) -> dict:
    """The operative cone-model fit: the ``isMostAccurate`` analysis, else the
    most recently submitted one. Returns ``{}`` when the CME has none yet."""
    fits = [a for a in analyses or [] if isinstance(a, dict)]
    if not fits:
        return {}
    for a in fits:
        if a.get("isMostAccurate"):
            return a
    return max(fits, key=lambda a: str(a.get("submissionTime") or ""))


def pick_enlil(enlil_list: list | None) -> dict:
    """The operative WSA-ENLIL run: prefer runs that predict an Earth arrival,
    then the most recently completed. Returns ``{}`` when none exist."""
    runs = [e for e in enlil_list or [] if isinstance(e, dict)]
    if not runs:
        return {}
    with_arrival = [e for e in runs if e.get("estimatedShockArrivalTime")]
    pool = with_arrival or runs
    return max(pool, key=lambda e: str(e.get("modelCompletionTime") or ""))


def _predicted_kp(enlil: dict) -> float | None:
    kps = [_num(enlil.get(k)) for k in ("kp_90", "kp_135", "kp_180")]
    kps = [k for k in kps if k is not None]
    return max(kps) if kps else None


def parse_cmes(raw: list) -> list[dict]:
    """Normalize the DONKI /WS/get/CME payload into flat catalog records.

    A record without a parseable ``startTime`` or ``activityID`` is dropped;
    everything else degrades to ``None`` field-by-field (DONKI entries are
    frequently incomplete right after an eruption).
    """
    out: list[dict] = []
    for cme in raw if isinstance(raw, list) else []:
        if not isinstance(cme, dict):
            continue
        activity_id = cme.get("activityID")
        start_time = _dt(cme.get("startTime"))
        if not activity_id or start_time is None:
            continue
        analysis = pick_analysis(cme.get("cmeAnalyses"))
        enlil = pick_enlil(analysis.get("enlilList"))
        arrival = _dt(enlil.get("estimatedShockArrivalTime"))
        try:
            active_region = int(cme["activeRegionNum"]) if cme.get("activeRegionNum") else None
        except (TypeError, ValueError):
            active_region = None
        out.append(
            {
                "activity_id": str(activity_id),
                "start_time": start_time,
                "source_location": cme.get("sourceLocation") or None,
                "active_region": active_region,
                "latitude": _num(analysis.get("latitude")),
                "longitude": _num(analysis.get("longitude")),
                "half_angle": _num(analysis.get("halfAngle")),
                "speed": _num(analysis.get("speed")),
                "cme_type": analysis.get("type") or None,
                "time21_5": _dt(analysis.get("time21_5")),
                "is_earth_directed": arrival is not None,
                "predicted_arrival_time": arrival,
                "predicted_kp": _predicted_kp(enlil),
                "note": cme.get("note") or "",
                "catalog_link": cme.get("link") or None,
            }
        )
    return out


async def fetch_cmes(start: date, end: date) -> list[dict]:
    """Catalog records for CMEs first observed in ``[start, end]`` (UTC dates)."""
    url = f"{settings.donki_base_url}/WS/get/CME"
    params = {"startDate": start.isoformat(), "endDate": end.isoformat()}
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(url, params=params)
        r.raise_for_status()
        # DONKI returns an empty body (not "[]") when the window has no CMEs.
        data = r.json() if r.content else []
    return parse_cmes(data)
