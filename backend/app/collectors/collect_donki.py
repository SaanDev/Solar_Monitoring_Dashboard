"""Fetch CMEs (with WSA-ENLIL arrival predictions) from NASA DONKI.

DONKI (Space Weather Database Of Notifications, Knowledge, Information) has a
public API on the main CCMC host that needs no API key:
  https://ccmc.gsfc.nasa.gov/DONKI-API/get/CME?startDate=YYYY-MM-DD&endDate=YYYY-MM-DD

It replaced kauai.ccmc.gsfc.nasa.gov/DONKI/WS/get/... on 2026-09-30 with the
same parameters and JSON (https://ccmc.gsfc.nasa.gov/news/major-updates). The
old host, and the api.nasa.gov/DONKI mirror that proxied it, now 301 to that
news page, so redirects are not followed: a 3xx from a JSON API means it moved.

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

# Where CCMC announces endpoint moves; quoted when the API answers with a redirect.
CCMC_NEWS_URL = "https://ccmc.gsfc.nasa.gov/news/major-updates"


class DonkiUnavailableError(RuntimeError):
    """The DONKI API was unreachable, has moved, or did not answer with a JSON
    list of CMEs. The message names the URL and the cause, ready to log as-is."""


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
    """Normalize the DONKI /get/CME payload into flat catalog records.

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


async def fetch_cmes(
    start: date, end: date, client: httpx.AsyncClient | None = None
) -> list[dict]:
    """Catalog records for CMEs first observed in ``[start, end]`` (UTC dates).

    Raises :class:`DonkiUnavailableError` when the API is unreachable, has moved
    (any 3xx), returns an HTTP error, or answers with anything but a JSON list.
    """
    if client is None:
        async with httpx.AsyncClient(timeout=30) as owned:
            return await fetch_cmes(start, end, owned)

    url = httpx.URL(
        f"{settings.donki_base_url.rstrip('/')}/get/CME",
        params={"startDate": start.isoformat(), "endDate": end.isoformat()},
    )
    try:
        r = await client.get(url)
    except httpx.HTTPError as exc:  # DNS, connect, TLS, timeout
        detail = f"{type(exc).__name__}: {exc}" if str(exc) else type(exc).__name__
        raise DonkiUnavailableError(f"DONKI API unreachable at {url} ({detail})") from exc

    if 300 <= r.status_code < 400:
        raise DonkiUnavailableError(
            f"DONKI API has moved: {url} answered HTTP {r.status_code} -> "
            f"{r.headers.get('location', '(no location)')}. Check {CCMC_NEWS_URL} "
            "for the new endpoint and set DONKI_BASE_URL"
        )
    if r.is_error:
        raise DonkiUnavailableError(f"DONKI API returned HTTP {r.status_code} for {url}")
    # The retired kauai service sent an empty body (not "[]") for a window with
    # no CMEs; keep accepting that.
    if not r.content:
        return []
    try:
        data = r.json()
    except ValueError as exc:
        ctype = r.headers.get("content-type", "no content-type")
        raise DonkiUnavailableError(
            f"DONKI API returned non-JSON ({ctype}) for {url}"
        ) from exc
    if not isinstance(data, list):
        raise DonkiUnavailableError(
            f"DONKI API returned a JSON {type(data).__name__}, not a CME list, for {url}"
        )
    return parse_cmes(data)
