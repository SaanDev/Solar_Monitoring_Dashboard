"""ML radio-burst scanner — detect solar radio bursts from e-CALLISTO data.

A scheduled pass enumerates newly-published e-CALLISTO ``.fit.gz`` segments
across **all** stations, scores each new one with the active burst model,
and persists the per-file result to ``radio_burst_detections``
(which doubles as the dedup registry). Detections then become ``radio_burst``
rows in the shared ``events`` table only when **confirmed by independent
stations** (``app.processing.burst_confirmation``): different sites flag the
burst with high confidence, with the Sun up, at overlapping times, and the
readings of every station observing — each weighted by its track record — make
a burst far likelier than chance. The events surface through the alert feed and
Events page with the stations whose readings support them and those that also
flagged them.

Which model runs here is a setting, not a per-request choice: it comes from the
Settings page's Automatic Burst Detection picker (persisted, falling back to
``radio_burst_model`` — see ``app/services/model_settings_service.py``). One
model at a time keeps the alert stream (and the scorecard derived from it)
internally comparable.

The detection record granularity is per file (Burst / No_Burst), plus a burst
type when the model types bursts (BnB does not); this module adds the
multi-station confirmation on top.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, time as time_cls, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.collectors.collect_ecallisto import FitsFile, list_day_files
from app.config import settings
from app.ml.registry import alert_min_probability_for, resolve_model
from app.processing.burst_confirmation import ConfirmedBurst, confirm_bursts
from app.repositories.event_repo import (
    delete_events_of_type_in_range,
    delete_events_of_type_since,
    query_range,
    upsert_events,
)
from app.repositories.notification_repo import record_sent, sent_severities
from app.repositories.radio_detection_repo import (
    detections_for_range,
    earliest_detection_start,
    processed_filenames_since,
    upsert_detections,
)
from app.repositories.status_repo import record_error, record_success
from app.services.burst_inference_client import predict_url
from app.services.station_reliability_service import confirmation_params, load_evidence

logger = logging.getLogger(__name__)

# Health name surfaced by /api/sources/status so a stalled real-time pipeline
# (e.g. the model microservice being down) is visible instead of silently
# producing no alerts.
SOURCE_NAME = "Radio-Burst-Scan"

# e-CALLISTO segments are ~15 minutes.
_SEGMENT = timedelta(minutes=15)
# How far back each event rebuild re-derives. Wider than the scan's max-age so
# an event keeps gaining stations as late files arrive over later passes.
_AGGREGATION_LOOKBACK = timedelta(hours=24)
# Files read on either side of a rebuild's range: a file that started before
# the range still overlaps it, and one just after it can extend an event.
_CONTEXT = timedelta(minutes=30)

# ``events.source`` for windows re-derived by the offline catch-up rather than by
# a live scan — provenance only. Suppressing their notifications does NOT rely on
# it (a later live rebuild of the same window would overwrite the value); the
# catch-up writes the sent-notification ledger instead.
LIVE_EVENT_SOURCE = "ml-model"
BACKFILL_EVENT_SOURCE = "ml-model-backfill"

# Version of the burst-confirmation rule. Bump it when a change should reach the
# stored history too: at startup a database whose bursts were derived by an
# older version re-derives them all once (``rederive_history_if_outdated``).
#   1 — multi-station confirmation (track-record-weighted evidence) replaces the
#       4-station / 15-minute-window rule.
RADIO_DERIVATION_VERSION = 1

_LEVEL_RANK = {"info": 0, "watch": 1, "warning": 2, "critical": 3}


# ── Pure helpers (unit-tested without DB / network) ──────────────────────────


def _utc(dt: datetime) -> datetime:
    """Naive datetimes (SQLite) are UTC."""
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)


def _odds(likelihood_ratio: float) -> str:
    """A likelihood ratio as compact odds: "54:1", "3,400:1", "2e+07:1"."""
    if likelihood_ratio >= 1e5:
        return f"{likelihood_ratio:.0e}:1"
    return f"{likelihood_ratio:,.0f}:1"


def _describe(
    burst: ConfirmedBurst,
    peak_probability: float,
    burst_type: str | None = None,
    model_name: str | None = None,
) -> str:
    """One-line event summary for the alert feed.

    The model name goes here rather than into ``events.source``: that table is
    keyed on ``(type, start_time)`` with no model dimension, so tagging the
    source per model would imply per-model events the schema cannot hold.
    """
    kind = f" {burst_type}" if burst_type else ""
    who = f", {model_name}" if model_name else ""
    also = burst.also_flagged_stations
    also_text = f"; also flagged by {', '.join(also)}" if also else ""
    return (
        f"Solar radio burst{kind} ({burst.start:%H:%M}–{burst.end:%H:%M} UTC) — "
        f"confirmed by {len(burst.sites)} sites: {', '.join(burst.confirming_stations)} "
        f"(evidence {_odds(burst.likelihood_ratio)}, peak p={peak_probability:.2f}{who}){also_text}"
    )


def _window_burst_type(items: list[dict]) -> str | None:
    """The burst's type: the one carried by the most confident detection.

    Stations see the same event with different signal quality, so the clearest
    view is the one to believe. Detections with no type simply do not vote.
    """
    typed = [i for i in items if i.get("burst_type")]
    if not typed:
        return None
    best = max(typed, key=lambda i: (i.get("type_confidence") or 0.0, i["probability"]))
    return best["burst_type"]


def burst_event(burst: ConfirmedBurst, model_name: str | None = None) -> dict:
    """A confirmed burst as a ``radio_burst`` events row.

    ``stations`` lists who confirmed it first, then sun-up stations that also
    flagged it (whose votes did not count), so the UI offers every spectrogram
    that shows the burst. ``peak_time`` is the peak file's start, clamped into
    the event: a whole-file model cannot place the burst inside its file.
    """
    peak = max(burst.confirming, key=lambda d: d["probability"])
    peak_time = min(max(_utc(peak["start_time"]), burst.start), burst.end)
    burst_type = _window_burst_type(burst.confirming + burst.also_flagged)
    return {
        "type": "radio_burst",
        "start_time": burst.start,
        "end_time": burst.end,
        "peak_time": peak_time,
        "peak_value": float(peak["probability"]),
        "severity": peak.get("alert_level") or "",
        "description": _describe(burst, float(peak["probability"]), burst_type, model_name),
        "stations": ",".join(burst.confirming_stations + burst.also_flagged_stations),
        # Structured type for the Timeline's color coding; None when nothing
        # in the burst was classifiable.
        "burst_type": burst_type,
        "source_url": None,
    }


def detection_row(file: FitsFile, record: dict) -> dict:
    """Map an inference record onto a ``radio_burst_detections`` row dict."""
    return {
        "filename": file.filename,
        "station": file.station,
        "start_time": file.start,
        "end_time": file.start + _SEGMENT,
        "focus": file.focus,
        "probability": float(record.get("burst_probability", 0.0)),
        "predicted_label": record.get("predicted_label", "No_Burst"),
        "alert_level": record.get("alert_level", ""),
        "model_id": record.get("model_id", ""),
        "burst_type": record.get("burst_type"),
        "type_confidence": record.get("type_confidence"),
        "type_model_id": record.get("type_model_id"),
    }


# ── Notification ledger ──────────────────────────────────────────────────────


def _overlaps(a: dict, b: dict) -> bool:
    a_end = a.get("end_time")
    b_end = b.get("end_time")
    return (a_end is None or _utc(a_end) > _utc(b["start_time"])) and (
        b_end is None or _utc(b_end) > _utc(a["start_time"])
    )


async def _carry_notifications(db: AsyncSession, before: list[dict], after: list[dict]) -> None:
    """Keep an already-announced burst announced when its start moves.

    An event's id is its start time, and a confirmed burst can start earlier on
    a later pass (a late station's file extends it), which would read as a new
    event and alert again. A new event overlapping one already in the ledger
    inherits that entry.
    """
    if not before or not after:
        return
    from app.services.event_service import event_id_for

    old_ids = {event_id_for(o): o for o in before}
    sent = await sent_severities(db, list(old_ids))
    if not sent:
        return
    new_ids = [event_id_for(e) for e in after]
    already = await sent_severities(db, new_ids)
    entries = []
    for e, eid in zip(after, new_ids):
        if eid in already:
            continue
        levels = [sent[oid] for oid, o in old_ids.items() if oid in sent and _overlaps(o, e)]
        if levels:
            entries.append((eid, max(levels, key=lambda lv: _LEVEL_RANK.get(lv, 0))))
    await record_sent(db, entries)


async def suppress_notifications(db: AsyncSession, events: list[dict]) -> None:
    """Mark re-derived (not live) events as already notified.

    A gap filled hours or days later — or history rebuilt under a new rule — must
    not replay as a burst of alerts, but the dispatcher works off the event feed,
    which is exactly where these events now live. Rather than teaching it about
    provenance (which a later live re-derivation would overwrite anyway — see
    ``BACKFILL_EVENT_SOURCE``), we write the sent-notification ledger up front, at
    the severity the alert *would* have had. Events already in the ledger are left
    alone, so a genuine escalation of an event announced live still goes out.
    """
    if not events:
        return
    from app.services.event_service import alert_level_for, event_id_for

    ids = [event_id_for(e) for e in events]
    already = await sent_severities(db, ids)
    pending = [
        (eid, alert_level_for("radio_burst", e.get("severity")))
        for eid, e in zip(ids, events)
        if eid not in already
    ]
    await record_sent(db, pending)


# ── Scan + persist ───────────────────────────────────────────────────────────


async def _score_files(files: list[FitsFile], model_id: str | None = None) -> list[dict]:
    """Score files concurrently (bounded); drop any that fail to score."""
    sem = asyncio.Semaphore(max(1, settings.radio_burst_concurrency))

    async def _one(f: FitsFile) -> dict | None:
        async with sem:
            record = await predict_url(f.url, filename=f.filename, model_id=model_id)
        return detection_row(f, record) if record is not None else None

    results = await asyncio.gather(*(_one(f) for f in files))
    return [r for r in results if r is not None]


async def rebuild_radio_burst_events(
    db: AsyncSession,
    since: datetime | None = None,
    until: datetime | None = None,
    source: str = LIVE_EVENT_SOURCE,
) -> list[dict]:
    """Re-derive ``radio_burst`` events starting in a window from the stored
    detections; returns the events that now stand for it.

    Defaults to the live scan's rolling lookback (the last
    ``_AGGREGATION_LOOKBACK``, open-ended at the top). The offline catch-up passes
    an explicit ``since``/``until`` so it can rebuild one historical day without
    touching anything newer.

    Re-derivation is authoritative for its window: events no longer confirmed —
    including ones derived by an older rule — are deleted rather than left in the
    feed. That is also why the deletion is bounded by ``until`` when one is given:
    a day-scoped rebuild must not sweep away events outside the day it re-derived.
    Rows of a retired model are judged by that model's own threshold until the
    backfill re-scores them.
    """
    spec = resolve_model()
    now = datetime.now(timezone.utc)
    start = since if since is not None else now - _AGGREGATION_LOOKBACK
    end = until if until is not None else now
    if end <= start:
        return []
    rows = await detections_for_range(db, start - _CONTEXT, end + _CONTEXT)
    evidence = await load_evidence(db)
    result = confirm_bursts(
        rows, evidence, confirmation_params(), burst_minimum=alert_min_probability_for
    )
    events = [
        burst_event(b, model_name=spec.name)
        for b in result.events
        if start <= b.start and (until is None or b.start < end)
    ]
    before = [
        e for e in await query_range(db, start, end) if e["type"] == "radio_burst"
    ]
    keep_starts = {e["start_time"] for e in events}
    if until is None:
        await delete_events_of_type_since(db, "radio_burst", start, keep_starts)
    else:
        await delete_events_of_type_in_range(db, "radio_burst", start, end, keep_starts)
    await upsert_events(db, events, source=source)
    await _carry_notifications(db, before, events)
    return events


async def rederive_history_if_outdated(db: AsyncSession) -> bool:
    """Rebuild every stored day's bursts when they predate
    ``RADIO_DERIVATION_VERSION``; returns whether it ran. Never raises: on a
    failure the version marker is left alone, so the next startup retries.

    History is re-derived day by day from the oldest stored detection, silently
    (the ledger is pre-filled — these are old events under a new rule, not news).
    """
    from app.repositories.app_settings_repo import get_or_create_settings

    try:
        row = await get_or_create_settings(db)
        if row.radio_burst_derivation_version >= RADIO_DERIVATION_VERSION:
            return False
        first = await earliest_detection_start(db)
        now = datetime.now(timezone.utc)
        total = days = 0
        if first is not None:
            day = first.date()
            while day <= now.date():
                d0 = datetime.combine(day, time_cls.min, tzinfo=timezone.utc)
                events = await rebuild_radio_burst_events(
                    db, since=d0, until=min(d0 + timedelta(days=1), now),
                    source=BACKFILL_EVENT_SOURCE,
                )
                await suppress_notifications(db, events)
                total += len(events)
                days += 1
                day += timedelta(days=1)
        row = await get_or_create_settings(db)
        row.radio_burst_derivation_version = RADIO_DERIVATION_VERSION
        await db.commit()
        logger.info(
            "radio-burst history re-derived (rule version %d): %d event(s) over %d day(s)",
            RADIO_DERIVATION_VERSION, total, days,
        )
        return True
    except Exception as exc:  # pragma: no cover - defensive, startup must not fail on this
        await db.rollback()
        logger.warning("radio-burst history re-derivation failed: %s", exc)
        return False


async def scan_and_detect_radio_bursts(db: AsyncSession) -> int:
    """Scan the archive for new files, score them, and refresh burst events.

    Resilient by design (mirrors ``event_service.detect_and_store``): archive or
    inference failures are recorded in ``source_status`` (so they show up in
    /api/sources/status) and the pass returns rather than raising, keeping the
    scheduler ticking. A model that never loaded — the usual reason "no alerts
    ever appear" — is reported explicitly instead of silently scoring nothing.
    """
    if not settings.radio_burst_enabled:
        return 0

    spec = resolve_model()
    now = datetime.now(timezone.utc)
    since = now - timedelta(hours=settings.radio_burst_max_age_hours)

    try:
        # Today + yesterday covers the UTC-midnight boundary.
        days = {now.date(), (now - timedelta(days=1)).date()}
        files: list[FitsFile] = []
        list_errors: list[str] = []
        for day in days:
            try:
                files.extend(await list_day_files(day))
            except Exception as exc:  # one bad day shouldn't sink the pass
                list_errors.append(str(exc))
                logger.warning("radio burst scan: listing %s failed: %s", day, exc)

        # Every listing failed -> the archive is unreachable; report and stop.
        if list_errors and len(list_errors) == len(days):
            await record_error(
                db, SOURCE_NAME, f"e-CALLISTO archive unreachable: {list_errors[0]}"
            )
            return 0

        # Only recent segments, and only ones not already scored.
        recent = [f for f in files if f.start >= since]
        todo_count = 0
        scored = 0
        if recent:
            # Dedup is per model: after the configured model changes, the recent
            # window is re-scored with the new one instead of being skipped.
            processed = await processed_filenames_since(db, since, model_id=spec.id)
            todo = [f for f in recent if f.filename not in processed]
            todo_count = len(todo)
            if todo:
                rows = await _score_files(todo, model_id=spec.id)
                scored = len(rows)
                if rows:
                    await upsert_detections(db, rows)
                logger.info(
                    "radio burst scan: scored %d/%d new files with %s",
                    scored, todo_count, spec.name,
                )

        written = len(await rebuild_radio_burst_events(db))
        if written:
            logger.info("radio burst scan: %d confirmed burst event(s)", written)

        # If there were files to score but none succeeded, inference is failing —
        # surface that, since it's why no alerts appear.
        if todo_count > 0 and scored == 0:
            await record_error(
                db,
                SOURCE_NAME,
                f"{spec.name} produced no results: scored 0/{todo_count} files "
                f"(check PyTorch is installed and the checkpoint loaded — see logs)",
            )
        else:
            await record_success(db, SOURCE_NAME)
        return written
    except Exception as exc:  # pragma: no cover - defensive, mirrors ingest runner
        await db.rollback()
        try:
            await record_error(db, SOURCE_NAME, str(exc))
        except Exception:
            pass
        logger.warning("radio burst scan failed: %s", exc)
        return 0
