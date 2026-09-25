"""On-demand daily burst prediction + comparison with the official burst list.

Mirrors the ``daily_burst_report.py`` workflow from the Burst Identifier project,
served through the dashboard: for a chosen UTC date (and optional station subset)
it scores every e-CALLISTO segment with the chosen model, clusters the burst
detections into time events (the same single-linkage ``cluster_events`` grouping,
10-min gap), and compares those predicted events against the published
e-CALLISTO burst list for that day.

Unlike the automatic scan, which is pinned to one configured model, a run here
names its own: ``model_id`` selects the binary classifier and ``classify_types``
toggles the burst-type stage. Both are fixed per job because they change the
scores; the ``raw`` event-selection mode is not, so it can be toggled on an
existing result without re-scoring.

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
from app.ml.registry import (
    UnknownModelError,
    alert_min_probability,
    classify_types_default,
    resolve_binary,
    resolve_type,
)
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
        "burst_type": row.get("burst_type"),
        "type_confidence": row.get("type_confidence"),
        # Typed region geometry, present only for freshly scored rows (it is not
        # persisted); stored real-time rows keep just the dominant type.
        "regions": row.get("type_regions") or [],
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
        "model_id": record.get("model_id", ""),
        "burst_type": record.get("burst_type"),
        "type_confidence": record.get("type_confidence"),
        "type_model_id": record.get("type_model_id"),
        "type_regions": record.get("type_regions") or [],
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


def start_prediction(
    day: date_cls,
    stations: list[str],
    raw: bool = False,
    model_id: str | None = None,
    classify_types: bool | None = None,
) -> str:
    """Create a prediction job and kick off scoring in the background.

    ``raw`` records the job's default event-selection mode (see
    :func:`assemble_result`). It only affects result assembly, not scoring — the
    same scored rows can be re-assembled in either mode without re-scoring.

    ``model_id`` and ``classify_types`` are fixed for the job's lifetime, since
    they *do* affect scoring: changing either means a new run.
    """
    spec = resolve_binary(model_id)
    wants_types = classify_types_default() if classify_types is None else bool(classify_types)
    job_id = uuid4().hex
    _JOBS[job_id] = {
        "job_id": job_id,
        "status": "running",
        "scanned": 0,
        "total": 0,
        "date": day.isoformat(),
        "stations": stations,
        "raw": raw,
        "model_id": spec.id,
        "classify_types": wants_types,
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
    model_id = job.get("model_id")
    classify_types = job.get("classify_types")

    async def _one(f: FitsFile) -> dict | None:
        async with sem:
            record = await predict_url(
                f.url,
                filename=f.filename,
                model_id=model_id,
                classify_types=classify_types,
            )
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


def _event_type(rows: list[dict]) -> tuple[str | None, dict[str, int]]:
    """An event's burst type plus how its detections voted.

    The type comes from the most confident typed detection rather than a majority:
    stations see the same event at different signal quality, so the clearest view
    is the one to believe. ``type_counts`` is returned alongside so the UI can show
    when stations disagreed.
    """
    typed = [d for d in rows if d.get("burst_type")]
    if not typed:
        return None, {}
    counts: dict[str, int] = {}
    for d in typed:
        counts[d["burst_type"]] = counts.get(d["burst_type"], 0) + 1
    best = max(typed, key=lambda d: (d.get("type_confidence") or 0.0, d["prob"]))
    return best["burst_type"], counts


def _build_predicted_event(index: int, detections: list[dict]) -> dict:
    rows = sorted(detections, key=lambda d: (d["seconds"], d["station"], d["focus"]))
    stations = sorted({d["station"] for d in rows})
    peak = max(rows, key=lambda d: d["prob"])
    dominant_type, type_counts = _event_type(rows)
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
        "dominant_type": dominant_type,
        "type_counts": type_counts,
        "matched_official": False,     # set during comparison
        "detections": [
            {
                "station": d["station"],
                "focus": d["focus"],
                "filename": d["filename"],
                "time": d["time"],
                "probability": d["prob"],
                "alert_level": d["alert"],
                "burst_type": d.get("burst_type"),
                "type_confidence": d.get("type_confidence"),
                "regions": d.get("regions") or [],
            }
            for d in rows
        ],
    }


async def assemble_result(
    rows: list[dict],
    day: date_cls,
    stations: list[str] | None = None,
    raw: bool = False,
    model_id: str | None = None,
    classify_types: bool | None = None,
) -> dict:
    """Build the prediction result from the scored rows + the official burst list.

    When ``stations`` is given (a non-empty selection), the official burst-list
    events are filtered to those that involve at least one selected station, so the
    comparison is scoped to what the user asked to predict. An empty/None selection
    (= all stations) keeps every official event.

    ``raw`` chooses how scored detections become predicted events:
      * ``False`` (event-selection criteria, default) — the live-alert filter: a
        detection must clear the alert probability minimum and a clustered event is
        kept only when corroborated across enough stations (see ``_is_corroborated``).
      * ``True`` (raw model output) — every segment the model labelled ``Burst`` is
        clustered into an event with no corroboration requirement. Use this when a
        narrow station selection can't meet the multi-station minimum, so genuine
        bursts would otherwise be hidden.

    ``model_id`` names the model that produced ``rows``. When omitted it is derived
    from the rows themselves (stored real-time detections carry it) — it matters
    because the criteria-mode probability minimum is per-model.
    """
    def _spec_for(candidate: str | None):
        """Resolve a model id, tolerating one written by a since-retired model."""
        try:
            return resolve_binary(candidate)
        except UnknownModelError:
            return resolve_binary()

    if model_id:
        # A job states which model scored its rows; that is authoritative.
        spec = _spec_for(model_id)
        per_row_gate = False
    else:
        # A day of *stored* detections can span two models, because switching the
        # configured scan model only re-scores the recent window. Attribute the day
        # to whichever model produced most rows, but gate each row by its own —
        # one threshold for the whole day would drop the other model's detections.
        counts: dict[str, int] = {}
        for r in rows:
            if r.get("model_id"):
                counts[r["model_id"]] = counts.get(r["model_id"], 0) + 1
        spec = _spec_for(max(counts, key=counts.get) if counts else None)
        per_row_gate = len(counts) > 1

    # Raw mode takes the model's own Burst decision as-is (its decision threshold
    # already gated the label); criteria mode additionally enforces the alert
    # probability minimum, which is the model's threshold unless overridden.
    default_min_prob = 0.0 if raw else alert_min_probability(spec)
    _min_prob_cache: dict[str, float] = {}

    def _min_prob_for(row: dict) -> float:
        if raw or not per_row_gate:
            return default_min_prob
        row_model = row.get("model_id") or spec.id
        if row_model not in _min_prob_cache:
            _min_prob_cache[row_model] = alert_min_probability(_spec_for(row_model))
        return _min_prob_cache[row_model]

    bursts = [
        _detection_dict(r)
        for r in rows
        if r["predicted_label"] == "Burst" and float(r["probability"]) >= _min_prob_for(r)
    ]
    events = cluster_events(bursts, EVENT_GAP_MINUTES)
    # Criteria mode keeps only corroborated events (same as the live alert filter);
    # raw mode keeps every clustered event so nothing the model flagged is dropped.
    if not raw:
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

    # Type tally across the burst files that got one, so the summary can show the
    # day's mix at a glance ("III x4, II x1").
    type_counts: dict[str, int] = {}
    for b in bursts:
        if b.get("burst_type"):
            type_counts[b["burst_type"]] = type_counts.get(b["burst_type"], 0) + 1
    typed = next((r for r in rows if r.get("type_model_id")), None)
    if classify_types is None:
        classify_types = typed is not None
    type_model_id = typed.get("type_model_id") if typed else (
        resolve_type().id if classify_types else None
    )

    return {
        "date": day.isoformat(),
        "raw": raw,
        "stations": sorted({r["station"] for r in rows}),
        "total_files": len(rows),
        "burst_count": len(bursts),
        "event_count": len(predicted),
        "events": predicted,
        "official_events": official,
        "official_count": len(official),
        "matched_count": matched_predicted,
        "model_id": spec.id,
        "model_name": spec.name,
        "classify_types": bool(classify_types),
        "type_model_id": type_model_id,
        "type_counts": type_counts,
    }
