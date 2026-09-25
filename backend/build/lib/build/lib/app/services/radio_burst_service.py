"""ML radio-burst scanner — detect solar radio bursts from e-CALLISTO data.

A scheduled pass enumerates newly-published e-CALLISTO ``.fit.gz`` segments
across **all** stations, scores each new one with the configured burst
classifier, and persists the per-file result to ``radio_burst_detections``
(which doubles as the dedup registry). Burst-positive detections are then
aggregated by 15-minute window into ``radio_burst`` rows in the shared
``events`` table, so they surface through the existing alert feed and Events
page with the list of stations that observed each burst.

Which model runs here is a setting, not a per-request choice: the binary
classifier comes from the Settings page's Automatic Burst Detection picker
(persisted, falling back to ``radio_burst_binary_model`` — see
``app/services/model_settings_service.py``), and ``radio_burst_classify_types``
decides whether each burst-positive file is also labelled with a burst type. One
model at a time keeps the alert stream (and the scorecard derived from it)
internally comparable; the on-demand Burst Detector page is where models get
compared side by side.

The detection record granularity is whole-spectrum binary (Burst / No_Burst)
plus an optional burst type; this module adds time-window grouping and
multi-station corroboration on top.
"""
from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.collectors.collect_ecallisto import FitsFile, list_day_files
from app.config import settings
from app.ml.registry import alert_min_probability, resolve_binary
from app.repositories.event_repo import (
    delete_events_of_type_in_range,
    delete_events_of_type_since,
    upsert_events,
)
from app.repositories.radio_detection_repo import (
    burst_positive_in_range,
    processed_filenames_since,
    upsert_detections,
)
from app.repositories.status_repo import record_error, record_success
from app.services.burst_inference_client import predict_url

logger = logging.getLogger(__name__)

# Health name surfaced by /api/sources/status so a stalled real-time pipeline
# (e.g. the model microservice being down) is visible instead of silently
# producing no alerts.
SOURCE_NAME = "Radio-Burst-Scan"

# e-CALLISTO segments are ~15 minutes; bursts are aggregated into the same
# quarter-hour window across stations.
_SEGMENT = timedelta(minutes=15)
# How far back each event rebuild aggregates burst-positive detections. Wider
# than the scan's max-age so a window keeps accumulating stations across passes.
_AGGREGATION_LOOKBACK = timedelta(hours=24)

# ``events.source`` for windows re-derived by the offline catch-up rather than by
# a live scan — provenance only. Suppressing their notifications does NOT rely on
# it (a later live rebuild of the same window would overwrite the value); the
# catch-up writes the sent-notification ledger instead.
LIVE_EVENT_SOURCE = "ml-model"
BACKFILL_EVENT_SOURCE = "ml-model-backfill"


# ── Pure helpers (unit-tested without DB / network) ──────────────────────────


def _floor_to_window(dt: datetime) -> datetime:
    """Floor a timestamp to its 15-minute UTC window start.

    Our timestamps are always UTC; a naive datetime (e.g. one read back from a
    backend that drops tzinfo, like SQLite) is treated as UTC rather than local
    time, so the window is never shifted by the server's timezone offset.
    """
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return dt.replace(minute=(dt.minute // 15) * 15, second=0, microsecond=0)


def _describe(
    window_start: datetime,
    stations: list[str],
    high_conf: int,
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
    return (
        f"Solar radio burst{kind} ({window_start.strftime('%H:%M')} UTC) — "
        f"{len(stations)} stations ({high_conf} high-confidence): "
        f"{', '.join(stations)} (peak p={peak_probability:.2f}{who})"
    )


def _window_burst_type(items: list[dict]) -> str | None:
    """The window's burst type: the one carried by the most confident detection.

    Stations see the same event with different signal quality, so the clearest
    view is the one to believe. Detections with no type (typing off, or nothing
    in-distribution to classify) simply do not vote.
    """
    typed = [i for i in items if i.get("burst_type")]
    if not typed:
        return None
    best = max(typed, key=lambda i: (i.get("type_confidence") or 0.0, i["probability"]))
    return best["burst_type"]


def aggregate_events(
    detections: list[dict], model_name: str | None = None
) -> list[dict]:
    """Group burst-positive detections into one ``radio_burst`` event per
    15-minute window — but only emit the window as an alert when it is
    **corroborated**: recorded by ``radio_burst_min_stations`` distinct stations
    with at least ``radio_burst_min_high_conf_stations`` of them above the
    high-confidence probability. This keeps the alert feed to strong, multi-station
    events rather than every single-station detection.

    ``model_name`` is stamped into each event's description, so the feed says
    which classifier produced the alert."""
    groups: dict[datetime, list[dict]] = defaultdict(list)
    for d in detections:
        groups[_floor_to_window(d["start_time"])].append(d)

    events: list[dict] = []
    for window_start, items in groups.items():
        stations = sorted({i["station"] for i in items})
        high_conf_stations = {
            i["station"]
            for i in items
            if i["probability"] > settings.radio_burst_high_conf_probability
        }
        if (
            len(stations) < settings.radio_burst_min_stations
            or len(high_conf_stations) < settings.radio_burst_min_high_conf_stations
        ):
            continue  # not corroborated enough to alert

        peak = max(items, key=lambda i: i["probability"])
        burst_type = _window_burst_type(items)
        events.append(
            {
                "type": "radio_burst",
                "start_time": window_start,
                "end_time": window_start + _SEGMENT,
                "peak_time": peak["start_time"],
                "peak_value": float(peak["probability"]),
                "severity": peak.get("alert_level") or "",
                "description": _describe(
                    window_start,
                    stations,
                    len(high_conf_stations),
                    peak["probability"],
                    burst_type=burst_type,
                    model_name=model_name,
                ),
                "stations": ",".join(stations),
                # Structured type for the Timeline's color coding; None when
                # nothing in the window was classifiable.
                "burst_type": burst_type,
                "source_url": None,
            }
        )
    return events


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
    """Re-derive ``radio_burst`` events from burst-positive detections in a window;
    returns the events that now stand for it.

    Defaults to the live scan's rolling lookback (the last
    ``_AGGREGATION_LOOKBACK``, open-ended at the top). The offline catch-up passes
    an explicit ``since``/``until`` so it can rebuild one historical day without
    touching anything newer.

    Re-derivation is authoritative for its window: events whose windows no longer
    pass the corroboration filter (``aggregate_events``) are deleted, so a window
    that was previously alerted but no longer qualifies — or events created before
    the filter existed — are cleaned out instead of lingering in the feed. That is
    also why the deletion is bounded by ``until`` when one is given: a day-scoped
    rebuild must not sweep away events outside the day it re-derived."""
    spec = resolve_binary()
    now = datetime.now(timezone.utc)
    start = since if since is not None else now - _AGGREGATION_LOOKBACK
    end = until if until is not None else now
    if end <= start:
        return []
    detections = await burst_positive_in_range(
        db, start, end, alert_min_probability(spec)
    )
    events = aggregate_events(detections, model_name=spec.name)
    keep_starts = {e["start_time"] for e in events}
    if until is None:
        await delete_events_of_type_since(db, "radio_burst", start, keep_starts)
    else:
        await delete_events_of_type_in_range(
            db, "radio_burst", start, end, keep_starts
        )
    await upsert_events(db, events, source=source)
    return events


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

    spec = resolve_binary()
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
            logger.info("radio burst scan: %d burst window event(s)", written)

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
