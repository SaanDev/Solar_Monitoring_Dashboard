"""Event/alert engine — derive discrete events from the persisted time-series.

The detection pass reads a recent window of GOES XRS / proton / Kp / Dst from
TimescaleDB (populated by the ingestion scheduler), runs the pure detectors in
``app.processing.event_detection``, and upserts the results into the ``events``
table. Reads are served from that table (Redis-cached). The alert feed is a view
over every event (the full history); *active* alerts are the subset that is
ongoing or only just subsided.

Events are derived from already-ingested data — there is no live fallback here
(unlike the numeric services); if the DB is empty the pass simply finds nothing.
"""
from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.cache import cache_get_json, cache_set_json
from app.models.timeseries import DstIndex, GoesProton, GoesXrs, KpIndex
from app.processing.event_chains import (
    CHAIN_MAX_SPAN,
    build_chains,
    chain_id_by_event,
    event_id as chain_event_id,
)
from app.processing.event_correlation import (
    FLARE_BURST_MAX_GAP,
    correlate_events,
    event_key,
)
from app.processing.event_detection import (
    detect_dst_storms,
    detect_kp_storms,
    detect_proton_events,
    detect_xray_flares,
)
from app.repositories.event_repo import (
    delete_events_of_type_since,
    earliest_inconsistent_start,
    query_active_or_recent,
    query_all,
    query_range,
    upsert_events,
)
from app.repositories.timeseries_repo import safe_query_range
from app.schemas.alert_schema import AlertResponse, EventChain, EventResponse

logger = logging.getLogger(__name__)

# How far back each detection pass scans. Wider than the ingest cadence so an
# event whose onset predates the last pass is still re-evaluated (and its
# end_time/peak updated) rather than missed.
LOOKBACK_DAYS = 3

# An alert stays *active* while its event is in progress and for this long after
# it subsides. The feed keeps every alert; this only scopes the headline count.
ALERT_LINGER = timedelta(hours=6)

_EVENTS_TTL = 60
_ALERTS_TTL = 30


def _event_id(e: dict) -> str:
    """Stable id for an event: its type and UTC start.

    One implementation, shared with the chain builder (which keys chains on the
    same string), so alert ids, chain ids and the sent-notification ledger cannot
    drift apart.
    """
    return chain_event_id(e)


def event_id_for(e: dict) -> str:
    """Public view of the event id — the key the notification ledger is keyed on."""
    return _event_id(e)


# ── Detection pass ───────────────────────────────────────────────────────────


@dataclass(frozen=True)
class _Derived:
    model: type
    field: str  # the column the detector reads
    detect: Callable[[list[dict]], list[dict]]
    # Data read *before* the window as context only, so an event already running
    # when the window opens is still seen from its real onset. Must exceed the
    # longest event of the type; flares last hours, storms and proton events days.
    lead_in: timedelta


_DERIVED: dict[str, _Derived] = {
    "xray_flare": _Derived(GoesXrs, "long_channel", detect_xray_flares, timedelta(days=1)),
    "proton_event": _Derived(GoesProton, "flux_gt10", detect_proton_events, timedelta(days=14)),
    "geomagnetic_storm_kp": _Derived(KpIndex, "kp", detect_kp_storms, timedelta(days=14)),
    "geomagnetic_storm_dst": _Derived(DstIndex, "dst", detect_dst_storms, timedelta(days=14)),
}


async def detect_and_store(db: AsyncSession, lookback_days: int = LOOKBACK_DAYS) -> int:
    """Run detection over the recent window and upsert events. Never raises.

    Re-derivation is authoritative for the window: an event whose onset is no
    longer produced this pass — e.g. a flare that read as "in progress" last pass
    but has since decayed and been re-segmented/ended — is deleted rather than
    left lingering with a stale ``end_time=None``. Reconciliation is skipped for a
    feed that returned no data (a transient read failure must not wipe history).

    The window also reaches back to the earliest row the rolling window can't keep
    consistent (see ``earliest_inconsistent_start``): an event still running past
    the lookback, which then keeps being updated in place, or rows left broken by
    downtime or by earlier versions of this pass. Once those are re-derived the
    window falls back to ``lookback_days``.
    """
    now = datetime.now(timezone.utc)
    window_start = now - timedelta(days=lookback_days)
    total = 0
    for etype, spec in _DERIVED.items():
        try:
            start = window_start
            repair_from = await earliest_inconsistent_start(db, etype, window_start)
            if repair_from is not None and repair_from < start:
                logger.info("re-deriving %s from %s (stale or overlapping rows)", etype, repair_from)
                start = repair_from
            total += await _rederive(db, etype, spec, start, now)
        except Exception as exc:  # pragma: no cover - defensive, mirrors ingest runner
            await db.rollback()
            logger.warning("event detection failed for %s: %s", etype, exc)
    logger.info("detection pass stored %d events", total)
    return total


async def _rederive(
    db: AsyncSession, etype: str, spec: _Derived, start: datetime, end: datetime
) -> int:
    """Make the stored ``etype`` events starting in ``[start, end]`` match a fresh
    detection over that range; returns the number of events written."""
    points = await safe_query_range(db, spec.model, start - spec.lead_in, end)
    first_sample = next((p["time"] for p in points if p.get(spec.field) is not None), None)
    if first_sample is None:
        return 0  # a feed we couldn't read: leave its events alone (see detect_and_store)
    events = [
        e
        for e in spec.detect(points)
        # A span already running at the first sample read has an onset we never
        # saw; the detector would date it to that sample, and as the window slid
        # each pass would store another fragment of one event under a new start.
        # The lead-in makes that only the event longer than it — skip it rather
        # than store a made-up onset.
        if e["start_time"] != first_sample
        # The lead-in is context: keep only events that reach into the range.
        and (e["end_time"] is None or _as_utc(e["end_time"]) >= start)
    ]
    await delete_events_of_type_since(db, etype, start, {e["start_time"] for e in events})
    return await upsert_events(db, events)


# ── Reads ────────────────────────────────────────────────────────────────────


def _related_ids(e: dict, related: dict) -> list[str]:
    return [_event_id(r) for r in related.get(event_key(e), [])]


def _as_utc(dt: datetime) -> datetime:
    """Rows come back tz-naive on SQLite (tests); treat naive as UTC."""
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _to_event_response(
    e: dict, related_ids: list[str] | None = None, chain_id: str | None = None
) -> EventResponse:
    return EventResponse(
        id=_event_id(e),
        type=e["type"],
        severity=e.get("severity"),
        start_time=e["start_time"],
        end_time=e.get("end_time"),
        peak_time=e.get("peak_time"),
        peak_value=e.get("peak_value"),
        description=e.get("description", ""),
        stations=[s for s in (e.get("stations") or "").split(",") if s],
        burst_type=e.get("burst_type"),
        related_event_ids=related_ids or [],
        source_url=e.get("source_url"),
        chain_id=chain_id,
    )


def _in_range(r: dict, start: datetime, end: datetime) -> bool:
    """An event overlaps the requested window."""
    return _as_utc(r["start_time"]) <= end and (
        r["end_time"] is None or _as_utc(r["end_time"]) >= start
    )


async def get_events(db: AsyncSession, start: datetime, end: datetime) -> list[EventResponse]:
    key = f"events:range:{start.isoformat()}:{end.isoformat()}"
    cached = await cache_get_json(key)
    if cached is not None:
        return [EventResponse.model_validate(d) for d in cached]

    # Read a window widened by the max chain span so an in-range event still links
    # to a partner outside the range — a flare-burst pair just past the edge, or a
    # storm whose driving CME launched days earlier (for the chain_id stamp).
    rows = await query_range(db, start - CHAIN_MAX_SPAN, end + FLARE_BURST_MAX_GAP)
    related = correlate_events(rows)
    chain_of = chain_id_by_event(build_chains(rows))
    in_range = [r for r in rows if _in_range(r, start, end)]
    events = [
        _to_event_response(r, _related_ids(r, related), chain_of.get(_event_id(r)))
        for r in in_range
    ]
    await cache_set_json(key, [e.model_dump(mode="json") for e in events], _EVENTS_TTL)
    return events


# ── Event chains (causal storylines, derived on read) ────────────────────────

_LEVEL_RANK = {"info": 0, "watch": 1, "warning": 2, "critical": 3}


def _chain_peak_severity(members: list[dict]) -> str:
    """Highest alert level among a chain's members (drives the UI accent)."""
    best = "info"
    for m in members:
        lvl = _alert_level(m["type"], m.get("severity"))
        if _LEVEL_RANK.get(lvl, 0) > _LEVEL_RANK[best]:
            best = lvl
    return best


async def get_event_chains(
    db: AsyncSession, start: datetime, end: datetime
) -> list[EventChain]:
    """Causal storylines with at least one member in ``[start, end]``, newest first.

    Reads a window widened by the max chain span so a storm still links back to the
    CME (and its flare) that drove it days earlier; membership is re-derived on read.
    """
    key = f"event-chains:{start.isoformat()}:{end.isoformat()}"
    cached = await cache_get_json(key)
    if cached is not None:
        return [EventChain.model_validate(d) for d in cached]

    rows = await query_range(db, start - CHAIN_MAX_SPAN, end + FLARE_BURST_MAX_GAP)
    related = correlate_events(rows)
    chains = build_chains(rows)

    result: list[EventChain] = []
    for c in chains:
        if not any(_in_range(m, start, end) for m in c["members"]):
            continue
        result.append(
            EventChain(
                chain_id=c["chain_id"],
                start_time=c["start_time"],
                end_time=c["end_time"],
                summary=c["summary"],
                peak_severity=_chain_peak_severity(c["members"]),
                event_ids=c["event_ids"],
                roles=c["roles"],
                events=[
                    _to_event_response(m, _related_ids(m, related), c["chain_id"])
                    for m in c["members"]
                ],
            )
        )
    await cache_set_json(key, [r.model_dump(mode="json") for r in result], _EVENTS_TTL)
    return result


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


def alert_level_for(event_type: str, severity: str | None) -> str:
    """Public view of the alert-level mapping.

    The offline burst catch-up needs the level an event *would* be announced at,
    to pre-fill the sent-notification ledger with the same value the dispatcher
    would compare against.
    """
    return _alert_level(event_type, severity)


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
    # Forecast-derived types: predictions cap at "warning" — only a measured
    # storm/flare can be "critical".
    if event_type in ("cme", "geomagnetic_storm_prediction"):
        n = _scale_number(severity) if severity.startswith("G") else 0
        return "warning" if n >= 3 else "watch"
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


async def get_active_alerts(db: AsyncSession) -> list[AlertResponse]:
    """Alerts for events in progress or that subsided within ``ALERT_LINGER``,
    newest first — what the headline "active alerts" count reflects.

    An open row is trusted as in progress: the detection pass re-derives, and so
    closes, any open row the rolling window would otherwise leave behind.
    """
    key = "alerts:active"
    cached = await cache_get_json(key)
    if cached is not None:
        return [AlertResponse.model_validate(d) for d in cached]

    now = datetime.now(timezone.utc)
    alerts = [_to_alert_response(r) for r in await query_active_or_recent(db, now - ALERT_LINGER)]
    await cache_set_json(key, [a.model_dump(mode="json") for a in alerts], _ALERTS_TTL)
    return alerts


def highest_alert_level(alerts: list[AlertResponse]) -> str | None:
    """The most severe level among ``alerts`` (None when there are none)."""
    return max((a.severity for a in alerts), key=lambda s: _LEVEL_RANK.get(s, 0), default=None)
