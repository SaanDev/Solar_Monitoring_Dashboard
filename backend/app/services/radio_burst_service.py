"""ML radio-burst scanner — detect solar radio bursts from e-CALLISTO data.

A scheduled pass enumerates newly-published e-CALLISTO ``.fit.gz`` segments
across **all** stations, scores each new one via the burst-classifier
microservice, and persists the per-file result to ``radio_burst_detections``
(which doubles as the dedup registry). Burst-positive detections are then
aggregated by 15-minute window into ``radio_burst`` rows in the shared
``events`` table, so they surface through the existing alert feed and Events
page with the list of stations that observed each burst.

The detection record granularity is whole-spectrum binary (Burst / No_Burst);
this module adds time-window grouping and multi-station corroboration on top.
"""
from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.collectors.collect_ecallisto import FitsFile, list_day_files
from app.config import settings
from app.repositories.event_repo import delete_events_of_type_since, upsert_events
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
    window_start: datetime, stations: list[str], high_conf: int, peak_probability: float
) -> str:
    return (
        f"Solar radio burst ({window_start.strftime('%H:%M')} UTC) — "
        f"{len(stations)} stations ({high_conf} high-confidence): "
        f"{', '.join(stations)} (peak p={peak_probability:.2f})"
    )


def aggregate_events(detections: list[dict]) -> list[dict]:
    """Group burst-positive detections into one ``radio_burst`` event per
    15-minute window — but only emit the window as an alert when it is
    **corroborated**: recorded by ``radio_burst_min_stations`` distinct stations
    with at least ``radio_burst_min_high_conf_stations`` of them above the
    high-confidence probability. This keeps the alert feed to strong, multi-station
    events rather than every single-station detection."""
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
        events.append(
            {
                "type": "radio_burst",
                "start_time": window_start,
                "end_time": window_start + _SEGMENT,
                "peak_time": peak["start_time"],
                "peak_value": float(peak["probability"]),
                "severity": peak.get("alert_level") or "",
                "description": _describe(
                    window_start, stations, len(high_conf_stations), peak["probability"]
                ),
                "stations": ",".join(stations),
                "source_url": None,
            }
        )
    return events


def _detection_row(file: FitsFile, record: dict) -> dict:
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
    }


# ── Scan + persist ───────────────────────────────────────────────────────────


async def _score_files(files: list[FitsFile]) -> list[dict]:
    """Score files concurrently (bounded); drop any that fail to score."""
    sem = asyncio.Semaphore(max(1, settings.radio_burst_concurrency))

    async def _one(f: FitsFile) -> dict | None:
        async with sem:
            record = await predict_url(f.url, filename=f.filename)
        return _detection_row(f, record) if record is not None else None

    results = await asyncio.gather(*(_one(f) for f in files))
    return [r for r in results if r is not None]


async def rebuild_radio_burst_events(db: AsyncSession) -> int:
    """Re-derive ``radio_burst`` events from recent burst-positive detections.

    Re-derivation is authoritative for the lookback window: events whose windows no
    longer pass the corroboration filter (``aggregate_events``) are deleted, so a
    window that was previously alerted but no longer qualifies — or events created
    before the filter existed — are cleaned out instead of lingering in the feed."""
    now = datetime.now(timezone.utc)
    since = now - _AGGREGATION_LOOKBACK
    detections = await burst_positive_in_range(
        db, since, now, settings.radio_burst_alert_min_probability
    )
    events = aggregate_events(detections)
    keep_starts = {e["start_time"] for e in events}
    await delete_events_of_type_since(db, "radio_burst", since, keep_starts)
    return await upsert_events(db, events, source="ml-model")


async def scan_and_detect_radio_bursts(db: AsyncSession) -> int:
    """Scan the archive for new files, score them, and refresh burst events.

    Resilient by design (mirrors ``event_service.detect_and_store``): archive or
    inference-service outages are recorded in ``source_status`` (so they show up
    in /api/sources/status) and the pass returns rather than raising, keeping the
    scheduler ticking. A down model microservice — the usual reason "no alerts
    ever appear" — is reported explicitly instead of silently scoring nothing.
    """
    if not settings.radio_burst_enabled:
        return 0

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
            processed = await processed_filenames_since(db, since)
            todo = [f for f in recent if f.filename not in processed]
            todo_count = len(todo)
            if todo:
                rows = await _score_files(todo)
                scored = len(rows)
                if rows:
                    await upsert_detections(db, rows)
                logger.info("radio burst scan: scored %d/%d new files", scored, todo_count)

        written = await rebuild_radio_burst_events(db)
        if written:
            logger.info("radio burst scan: %d burst window event(s)", written)

        # If there were files to score but none succeeded, inference is failing —
        # surface that, since it's why no alerts appear.
        if todo_count > 0 and scored == 0:
            await record_error(
                db,
                SOURCE_NAME,
                f"burst inference produced no results: scored 0/{todo_count} files "
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
