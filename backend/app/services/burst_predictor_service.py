"""On-demand daily burst prediction + comparison with the official burst list.

Mirrors the ``daily_burst_report.py`` workflow from the Burst Identifier project,
served through the dashboard: for a chosen UTC date (and optional station subset)
it scores every e-CALLISTO segment with the trained model (via the inference
microservice), clusters the burst detections into time events (the same
single-linkage ``cluster_events`` grouping, 10-min gap), and compares those
predicted events against the published e-CALLISTO burst list for that day.

This is a self-contained, ephemeral tool: scoring runs as a background job whose
results live **in memory** on the job record — it needs neither the database nor
the live-monitoring ``radio_burst_detections`` table (so it works even when
Postgres is down, and never pollutes that table with arbitrary past-day rows).
The job registry is in-process — fine for the single-worker backend; a multi-worker
deployment would move it to Redis.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import date as date_cls, datetime, timedelta, timezone
from uuid import uuid4

from app.collectors.collect_ecallisto import FitsFile, list_day_files
from app.config import settings
from app.services.burst_inference_client import predict_url
from app.services.ecallisto_service import get_burst_events_for_date

logger = logging.getLogger(__name__)

# Detections within this many minutes of each other form one event (matches
# daily_burst_report.EVENT_GAP_MINUTES).
EVENT_GAP_MINUTES = 10
# Padding when matching a predicted event against an official burst-list window.
_MATCH_TOLERANCE_S = 5 * 60
_SEGMENT = timedelta(minutes=15)
# A detection flags a whole ~15-min segment, so its time window extends this many
# seconds past the segment's start (used for display + official-list matching).
_SEGMENT_SECONDS = int(_SEGMENT.total_seconds())

# job_id -> {status, scanned, total, date, stations, error, rows, finished_at}
_JOBS: dict[str, dict] = {}
_MAX_JOBS = 32  # keep the registry small; evict oldest finished jobs


# ── Event clustering (ported from daily_burst_report.cluster_events) ──────────


def cluster_events(detections: list[dict], gap_minutes: float) -> list[list[dict]]:
    """Group burst detections into events by start-time proximity.

    Detections (across all selected stations) are sorted by UTC start second and
    split into a new event whenever the gap to the previous detection exceeds
    ``gap_minutes`` (single-linkage), so one solar event seen by several stations
    in the same window lands in one cluster. Returned events are time-ordered.
    """
    if not detections:
        return []
    gap_seconds = float(gap_minutes) * 60.0
    ordered = sorted(detections, key=lambda d: (d["seconds"], d["station"]))
    events: list[list[dict]] = [[ordered[0]]]
    for det in ordered[1:]:
        if det["seconds"] - events[-1][-1]["seconds"] <= gap_seconds:
            events[-1].append(det)
        else:
            events.append([det])
    return events


# ── Helpers ───────────────────────────────────────────────────────────────────


def _seconds_of(dt: datetime) -> int:
    return dt.hour * 3600 + dt.minute * 60 + dt.second


def _hhmmss(dt: datetime) -> str:
    return dt.strftime("%H:%M:%S")


def _seconds_to_hhmm(seconds: int) -> str:
    seconds %= 86400
    return f"{seconds // 3600:02d}:{(seconds % 3600) // 60:02d}"


def _detection_dict(row: dict) -> dict:
    """Map a scored-file row to a clustering/response detection."""
    start = row["start_time"]
    return {
        "station": row["station"],
        "focus": row.get("focus", ""),
        "filename": row["filename"],
        "time": _hhmmss(start),
        "seconds": _seconds_of(start),
        "prob": float(row["probability"]),
        "alert": row.get("alert_level", ""),
    }


def _row_for(file: FitsFile, record: dict) -> dict:
    return {
        "filename": file.filename,
        "station": file.station,
        "start_time": file.start,
        "focus": file.focus,
        "probability": float(record.get("burst_probability", 0.0)),
        "predicted_label": record.get("predicted_label", "No_Burst"),
        "alert_level": record.get("alert_level", ""),
    }


def _hhmm_to_seconds(hhmm: str) -> int | None:
    try:
        h, m = hhmm.split(":")[:2]
        return int(h) * 3600 + int(m) * 60
    except (ValueError, AttributeError):
        return None


def _overlaps(a0: int, a1: int, b0: int, b1: int, tol: int = _MATCH_TOLERANCE_S) -> bool:
    return a0 - tol <= b1 and b0 - tol <= a1


# ── Job lifecycle ─────────────────────────────────────────────────────────────


def _evict_old_jobs() -> None:
    if len(_JOBS) <= _MAX_JOBS:
        return
    finished = [
        (jid, j) for jid, j in _JOBS.items() if j["status"] in ("done", "error")
    ]
    finished.sort(key=lambda kv: kv[1].get("finished_at") or 0)
    for jid, _ in finished[: len(_JOBS) - _MAX_JOBS]:
        _JOBS.pop(jid, None)


def start_prediction(day: date_cls, stations: list[str]) -> str:
    """Create a prediction job and kick off scoring in the background."""
    job_id = uuid4().hex
    _JOBS[job_id] = {
        "job_id": job_id,
        "status": "running",
        "scanned": 0,
        "total": 0,
        "date": day.isoformat(),
        "stations": stations,
        "error": None,
        "rows": [],
        "finished_at": None,
    }
    _evict_old_jobs()
    asyncio.create_task(_run_job(job_id, day, stations))
    return job_id


def get_job(job_id: str) -> dict | None:
    return _JOBS.get(job_id)


async def _score_files(files: list[FitsFile], job: dict) -> list[dict]:
    """Score files concurrently (bounded), updating job progress as each finishes."""
    sem = asyncio.Semaphore(max(1, settings.radio_burst_concurrency))

    async def _one(f: FitsFile) -> dict | None:
        async with sem:
            record = await predict_url(f.url, filename=f.filename)
        job["scanned"] += 1
        return _row_for(f, record) if record is not None else None

    results = await asyncio.gather(*(_one(f) for f in files))
    return [r for r in results if r is not None]


async def _run_job(job_id: str, day: date_cls, stations: list[str]) -> None:
    job = _JOBS[job_id]
    try:
        files = await list_day_files(day)
        if stations:
            wanted = set(stations)
            files = [f for f in files if f.station in wanted]
        # Cap is a safety valve only; 0 (default) processes every available segment.
        cap = settings.radio_burst_predict_max_files
        if cap and cap > 0:
            files = files[:cap]
        job["total"] = len(files)
        job["rows"] = await _score_files(files, job)
        job["status"] = "done"
    except Exception as exc:  # noqa: BLE001 - report failures via job status
        logger.warning("burst prediction job %s failed: %s", job_id, exc)
        job["status"] = "error"
        job["error"] = str(exc)
    finally:
        job["finished_at"] = datetime.now(timezone.utc).timestamp()


# ── Result assembly (from the job's in-memory rows + the official list) ────────


def _is_corroborated(cluster: list[dict]) -> bool:
    """Same multi-station corroboration the live alert pipeline applies: the
    cluster must span >= radio_burst_min_stations distinct stations with at least
    radio_burst_min_high_conf_stations of them above the high-confidence
    probability. Keeps predicted *events* to strong, corroborated bursts."""
    stations = {d["station"] for d in cluster}
    high_conf = {
        d["station"]
        for d in cluster
        if d["prob"] > settings.radio_burst_high_conf_probability
    }
    return (
        len(stations) >= settings.radio_burst_min_stations
        and len(high_conf) >= settings.radio_burst_min_high_conf_stations
    )


def _build_predicted_event(index: int, detections: list[dict]) -> dict:
    rows = sorted(detections, key=lambda d: (d["seconds"], d["station"], d["focus"]))
    stations = sorted({d["station"] for d in rows})
    peak = max(rows, key=lambda d: d["prob"])
    # Each detection covers a ~15-min segment, so the event window runs from the
    # first segment's start to the last segment's *end* (start + 15 min).
    start_seconds = rows[0]["seconds"]
    end_seconds = rows[-1]["seconds"] + _SEGMENT_SECONDS
    return {
        "index": index,
        "start": rows[0]["time"][:5],            # HH:MM
        "end": _seconds_to_hhmm(end_seconds),
        "start_seconds": start_seconds,
        "end_seconds": end_seconds,
        "n_stations": len(stations),
        "n_detections": len(rows),
        "stations": stations,
        "max_probability": peak["prob"],
        "alert_level": peak["alert"],
        "matched_official": False,     # set during comparison
        "detections": [
            {
                "station": d["station"],
                "focus": d["focus"],
                "filename": d["filename"],
                "time": d["time"],
                "probability": d["prob"],
                "alert_level": d["alert"],
            }
            for d in rows
        ],
    }


async def assemble_result(
    rows: list[dict], day: date_cls, stations: list[str] | None = None
) -> dict:
    """Build the prediction result from the scored rows + the official burst list.

    When ``stations`` is given (a non-empty selection), the official burst-list
    events are filtered to those that involve at least one selected station, so the
    comparison is scoped to what the user asked to predict. An empty/None selection
    (= all stations) keeps every official event.
    """
    min_prob = settings.radio_burst_alert_min_probability
    bursts = [
        _detection_dict(r)
        for r in rows
        if r["predicted_label"] == "Burst" and float(r["probability"]) >= min_prob
    ]
    events = cluster_events(bursts, EVENT_GAP_MINUTES)
    # Predict only corroborated events (same criteria as the live alert filter).
    events = [ev for ev in events if _is_corroborated(ev)]
    predicted = [_build_predicted_event(i + 1, ev) for i, ev in enumerate(events)]

    # Official e-CALLISTO burst list for the day, with two-way match flags. Scope
    # to the selected stations when a selection was made (case-insensitive).
    selected = {s.strip().lower() for s in (stations or []) if s and s.strip()}
    official_resp = await get_burst_events_for_date(day)
    official: list[dict] = []
    for ev in official_resp.events:
        if selected and not (selected & {s.strip().lower() for s in ev.stations}):
            continue  # event involves none of the selected stations
        o0 = _hhmm_to_seconds(ev.start)
        o1 = _hhmm_to_seconds(ev.end)
        matched = False
        if o0 is not None and o1 is not None:
            for pe in predicted:
                if _overlaps(pe["start_seconds"], pe["end_seconds"], o0, o1):
                    pe["matched_official"] = True
                    matched = True
        official.append(
            {
                "start": ev.start,
                "end": ev.end,
                "burst_type": ev.burst_type,
                "stations": ev.stations,
                "matched_prediction": matched,
            }
        )

    matched_predicted = sum(1 for pe in predicted if pe["matched_official"])
    return {
        "date": day.isoformat(),
        "stations": sorted({r["station"] for r in rows}),
        "total_files": len(rows),
        "burst_count": len(bursts),
        "event_count": len(predicted),
        "events": predicted,
        "official_events": official,
        "official_count": len(official),
        "matched_count": matched_predicted,
    }
