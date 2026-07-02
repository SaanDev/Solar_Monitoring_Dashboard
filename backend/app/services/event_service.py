"""Event/alert engine — derive discrete events from the persisted time-series.

The detection pass reads a recent window of GOES XRS / proton / Kp / Dst from
TimescaleDB (populated by the ingestion scheduler), runs the pure detectors in
``app.processing.event_detection``, and upserts the results into the ``events``
table. Reads are served from that table (Redis-cached); alerts are a live *view*
over events that are ongoing or only just subsided.

Events are derived from already-ingested data — there is no live fallback here
(unlike the numeric services); if the DB is empty the pass simply finds nothing.
"""
from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.cache import cache_get_json, cache_set_json
from app.models.timeseries import DstIndex, GoesProton, GoesXrs, KpIndex
from app.processing.event_correlation import (
    FLARE_BURST_MAX_GAP,
    correlate_events,
    event_key,
)
from app.processing.event_detection import detect_events
from app.repositories.event_repo import (
    delete_events_of_type_since,
    query_all,
    query_range,
    upsert_events,
)
from app.repositories.timeseries_repo import safe_query_range
from app.schemas.alert_schema import AlertResponse, EventResponse

logger = logging.getLogger(__name__)

# How far back each detection pass scans. Wider than the ingest cadence so an
# event whose onset predates the last pass is still re-evaluated (and its
# end_time/peak updated) rather than missed.
LOOKBACK_DAYS = 3

_EVENTS_TTL = 60
_ALERTS_TTL = 30


def _event_id(e: dict) -> str:
    return f"{e['type']}:{e['start_time'].isoformat()}"


# ── Detection pass ───────────────────────────────────────────────────────────


async def detect_and_store(db: AsyncSession, lookback_days: int = LOOKBACK_DAYS) -> int:
    """Run detection over the recent window and upsert events. Never raises.

    Re-derivation is authoritative for the window: an event whose onset is no
    longer produced this pass — e.g. a flare that read as "in progress" last pass
    but has since decayed and been re-segmented/ended — is deleted rather than
    left lingering with a stale ``end_time=None``. Reconciliation is skipped for a
    feed that returned no data (a transient read failure must not wipe history).
    """
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=lookback_days)
    try:
        series = {
            "xray_flare": await safe_query_range(db, GoesXrs, start, end),
            "proton_event": await safe_query_range(db, GoesProton, start, end),
            "geomagnetic_storm_kp": await safe_query_range(db, KpIndex, start, end),
            "geomagnetic_storm_dst": await safe_query_range(db, DstIndex, start, end),
        }
        events = detect_events(
            series["xray_flare"],
            series["proton_event"],
            series["geomagnetic_storm_kp"],
            series["geomagnetic_storm_dst"],
        )
        keep_starts: dict[str, set[datetime]] = defaultdict(set)
        for e in events:
            keep_starts[e["type"]].add(e["start_time"])
        for etype, points in series.items():
            if points:  # only reconcile a feed we actually read (see docstring)
                await delete_events_of_type_since(db, etype, start, keep_starts[etype])
        count = await upsert_events(db, events)
        logger.info("detection pass stored %d events", count)
        return count
    except Exception as exc:  # pragma: no cover - defensive, mirrors ingest runner
        await db.rollback()
        logger.warning("event detection failed: %s", exc)
        return 0


# ── Reads ────────────────────────────────────────────────────────────────────


def _related_ids(e: dict, related: dict) -> list[str]:
    return [_event_id(r) for r in related.get(event_key(e), [])]


def _as_utc(dt: datetime) -> datetime:
    """Rows come back tz-naive on SQLite (tests); treat naive as UTC."""
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _to_event_response(e: dict, related_ids: list[str] | None = None) -> EventResponse:
    return EventResponse(
        id=_event_id(e),
        type=e["type"],
        severity=e.get("severity"),
        start_time=e["start_time"],
        end_time=e.get("end_time"),
        peak_time=e.get("peak_time"),
        peak_value=e.get("peak_value"),
        description=e.get("description", ""),
        related_event_ids=related_ids or [],
        source_url=e.get("source_url"),
    )


async def get_events(db: AsyncSession, start: datetime, end: datetime) -> list[EventResponse]:
    key = f"events:range:{start.isoformat()}:{end.isoformat()}"
    cached = await cache_get_json(key)
    if cached is not None:
        return [EventResponse.model_validate(d) for d in cached]

    # Read a window widened by the correlation gap so an in-range event still
    # links to a partner sitting just outside the requested range.
    rows = await query_range(db, start - FLARE_BURST_MAX_GAP, end + FLARE_BURST_MAX_GAP)
    related = correlate_events(rows)
    in_range = [
        r
        for r in rows
        if _as_utc(r["start_time"]) <= end
        and (r["end_time"] is None or _as_utc(r["end_time"]) >= start)
    ]
    events = [_to_event_response(r, _related_ids(r, related)) for r in in_range]
    await cache_set_json(key, [e.model_dump(mode="json") for e in events], _EVENTS_TTL)
    return events


# ── Alerts (a view over current / recently-ended events) ─────────────────────

_FLARE_LEVEL = {"X": "critical", "M": "warning", "C": "watch"}
_DST_LEVEL = {
    "Super storm": "critical",
    "Intense storm": "warning",
    "Moderate storm": "watch",
    "Possible storm": "watch",   # pre-storm "possible geomagnetic storm" (Dst <= -30)
    "Weak storm": "info",
}
# Radio-burst severity mirrors the model's probability bands (see the inference
# service's ``probability_to_alert_level``).
_RADIO_LEVEL = {
    "High-confidence burst": "warning",
    "Likely burst": "watch",
    "Possible burst": "info",
}


def _alert_level(event_type: str, severity: str | None) -> str:
    """Map an event's classification to an alert severity the UI understands
    ("info" | "watch" | "warning" | "critical")."""
    if not severity:
        return "info"
    if event_type == "xray_flare":
        return _FLARE_LEVEL.get(severity[0], "info")
    if event_type == "proton_event":  # S1..S5
        n = _scale_number(severity)
        return "critical" if n >= 3 else "warning" if n == 2 else "watch"
    if event_type == "geomagnetic_storm_kp":  # G1..G5
        n = _scale_number(severity)
        return "critical" if n >= 4 else "warning" if n == 3 else "watch"
    if event_type == "geomagnetic_storm_dst":
        return _DST_LEVEL.get(severity, "info")
    if event_type == "radio_burst":
        return _RADIO_LEVEL.get(severity, "info")
    return "info"


def _scale_number(severity: str) -> int:
    try:
        return int(severity[1:])
    except (ValueError, IndexError):
        return 0


def _to_alert_response(e: dict, related_ids: list[str] | None = None) -> AlertResponse:
    ongoing = e.get("end_time") is None
    state = "in progress" if ongoing else "subsided"
    return AlertResponse(
        id=f"alert:{_event_id(e)}",
        type=e["type"],
        severity=_alert_level(e["type"], e.get("severity")),
        message=f"{e.get('description', '')} ({state})",
        timestamp=e.get("peak_time") or e["start_time"],
        source=e.get("source", "derived"),
        related_event_ids=related_ids or [],
    )


async def get_latest_alerts(db: AsyncSession) -> list[AlertResponse]:
    """The full alert/event history, newest first (nothing is dropped by age)."""
    key = "alerts:latest"
    cached = await cache_get_json(key)
    if cached is not None:
        return [AlertResponse.model_validate(d) for d in cached]

    rows = await query_all(db)
    related = correlate_events(rows)
    alerts = [_to_alert_response(r, _related_ids(r, related)) for r in rows]
    await cache_set_json(key, [a.model_dump(mode="json") for a in alerts], _ALERTS_TTL)
    return alerts
