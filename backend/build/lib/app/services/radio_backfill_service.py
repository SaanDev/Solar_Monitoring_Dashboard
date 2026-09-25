"""Offline catch-up: score the archive days the dashboard was not running for.

The live scanner (``radio_burst_service.scan_and_detect_radio_bursts``) only ever
looks at the last ``radio_burst_max_age_hours`` of e-CALLISTO data. That is the
right behaviour for alerting, but it means every hour the backend is down is an
hour that never gets scored — a permanent hole in the Timeline's model-burst lane,
in the Events feed, and in the correlation histograms, which are all derived from
``radio_burst_detections``.

This module closes those holes. It walks a range of UTC days, and for each one
compares the archive's directory listing against the filenames already scored
(**by any model** — see ``filenames_in_range``), scores whatever is missing with
the currently selected classifier, then re-derives that day's ``radio_burst``
events. Coverage is recorded per day in ``radio_burst_backfill_days`` so the next
pass skips finished days without touching the network.

Three properties matter more than speed here:

* **Resumable.** Work is chunked and every chunk is committed, so a restart
  mid-day resumes from the archive listing minus what is already stored, not from
  the beginning. Nothing is held in memory that a crash would lose.
* **Silent.** Filling a week-old gap must not fire a week of Telegram alerts. Events
  the catch-up creates are recorded in the sent-notification ledger up front, so
  the dispatcher treats them as already delivered (see ``_suppress_notifications``).
* **Out of the live scanner's way.** The catch-up never touches the last
  ``radio_burst_max_age_hours``; that window belongs to the live scan, which is
  what raises real-time alerts. So today's row stays ``partial`` by design.

One job runs at a time (in-process, like the Burst Detector's job registry — fine
for the single-worker backend; a multi-worker deployment would move it to Redis).
"""
from __future__ import annotations

import asyncio
import logging
import math
from datetime import date as date_cls, datetime, time as time_cls, timedelta, timezone
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.collectors.collect_ecallisto import FitsFile, list_day_files
from app.config import settings
from app.database import AsyncSessionLocal
from app.ml.registry import resolve_binary
from app.models.radio_backfill import (
    STATE_DONE,
    STATE_ERROR,
    STATE_PARTIAL,
    STATE_RUNNING,
)
from app.repositories.notification_repo import record_sent, sent_severities
from app.repositories.radio_backfill_repo import days_in_range, upsert_day
from app.repositories.radio_detection_repo import filenames_in_range, upsert_detections
from app.services.radio_burst_service import (
    BACKFILL_EVENT_SOURCE,
    detection_row,
    rebuild_radio_burst_events,
)

logger = logging.getLogger(__name__)

# Files scored between commits. Small enough that a restart loses little work,
# large enough that the per-chunk DB round-trip is noise next to the downloads.
_CHUNK = 60

# A handful of segments in a day can be unreadable (truncated uploads, station
# faults) and would otherwise keep the day open for retry forever. A day this
# close to fully covered counts as finished.
_COMPLETE_RATIO = 0.98

# The single in-process job. ``_job`` is the snapshot the API serves — it outlives
# the task so the UI can still show how the last run ended.
_job: dict | None = None
_task: asyncio.Task | None = None
_cancel = False


class BackfillBusyError(Exception):
    """A catch-up run is already in progress."""


# ── Day arithmetic ───────────────────────────────────────────────────────────


def _day_bounds(day: date_cls) -> tuple[datetime, datetime]:
    start = datetime.combine(day, time_cls.min, tzinfo=timezone.utc)
    return start, start + timedelta(days=1)


def _live_cutoff(now: datetime | None = None) -> datetime:
    """Start of the window the *live* scanner owns; the catch-up stops here."""
    now = now or datetime.now(timezone.utc)
    return now - timedelta(hours=settings.radio_burst_max_age_hours)


def _is_complete(covered: int, archive: int) -> bool:
    """Is a fully-elapsed day covered enough to stop revisiting it?"""
    if archive <= 0:
        return True  # the archive published nothing that day; nothing to score
    return covered >= math.ceil(archive * _COMPLETE_RATIO)


# ── Planning ─────────────────────────────────────────────────────────────────


async def plan_days(
    db: AsyncSession, first: date_cls, last: date_cls, force: bool = False
) -> list[date_cls]:
    """Days in ``[first, last]`` that still need work, **newest first**.

    Newest first because a gap that just opened is the one distorting the current
    picture; a month-old day can wait for the run to get to it.

    Without ``force`` this trusts the coverage ledger: a day already recorded as
    ``done`` is skipped with no network call at all, which is what makes the
    hourly gap check nearly free. A day with no ledger row is *not* assumed
    missing — it is inspected, and if the detections are already there it is
    simply recorded as done. ``force`` re-scores every day in the range with the
    currently selected model, ledger and existing rows notwithstanding.
    """
    rows = await days_in_range(db, first, last)
    today = datetime.now(timezone.utc).date()
    days: list[date_cls] = []
    day = last
    while day >= first:
        row = rows.get(day)
        stale = day >= today  # today is still being published; never final
        if force or stale or row is None or row["state"] != STATE_DONE:
            days.append(day)
        day -= timedelta(days=1)
    return days


# ── Scoring one day ──────────────────────────────────────────────────────────


async def _score_chunk(files: list[FitsFile], model_id: str) -> list[dict]:
    """Score a chunk concurrently; files that fail to download/score are dropped."""
    from app.services.burst_inference_client import predict_url

    sem = asyncio.Semaphore(max(1, settings.radio_burst_backfill_concurrency))

    async def _one(f: FitsFile) -> dict | None:
        async with sem:
            record = await predict_url(f.url, filename=f.filename, model_id=model_id)
        return detection_row(f, record) if record is not None else None

    results = await asyncio.gather(*(_one(f) for f in files))
    return [r for r in results if r is not None]


async def _suppress_notifications(db: AsyncSession, events: list[dict]) -> None:
    """Mark backfilled events as already notified.

    A gap filled hours or days later must not replay as a burst of alerts, but the
    dispatcher works off the event feed, which is exactly where these events now
    live. Rather than teaching it about provenance (which a later live re-derivation
    would overwrite anyway — see ``BACKFILL_EVENT_SOURCE``), we write the
    sent-notification ledger up front, at the severity the alert *would* have had.
    Events already in the ledger are left alone, so a genuine escalation of an
    event that was announced live still goes out.
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


async def process_day(
    db: AsyncSession, day: date_cls, force: bool = False, job: dict | None = None
) -> dict:
    """Score every unscored segment of ``day`` and rebuild that day's events.

    Returns the day's coverage row. Raises only on an unreachable archive listing
    (the caller records that as the day's error); individual file failures are
    counted, not raised, so one bad segment never sinks a day.
    """
    day_start, day_end = _day_bounds(day)
    # Everything from here on belongs to the live scanner, which is the only thing
    # allowed to raise real-time alerts.
    end_bound = min(day_end, _live_cutoff())
    spec = resolve_binary()

    files = await list_day_files(day)
    archive_files = [f for f in files if day_start <= f.start < day_end]
    in_scope = [f for f in archive_files if f.start < end_bound]

    await upsert_day(db, day, state=STATE_RUNNING, model_id=spec.id, error=None)

    covered = await filenames_in_range(db, day_start, day_end)
    todo = in_scope if force else [f for f in in_scope if f.filename not in covered]
    todo.sort(key=lambda f: f.start)

    if job is not None:
        job["day_files_total"] = len(todo)
        job["day_files_done"] = 0

    scored = failed = 0
    for i in range(0, len(todo), _CHUNK):
        if _cancel:
            break
        chunk = todo[i : i + _CHUNK]
        rows = await _score_chunk(chunk, spec.id)
        if rows:
            await upsert_detections(db, rows)
        scored += len(rows)
        failed += len(chunk) - len(rows)
        if job is not None:
            job["day_files_done"] += len(chunk)
            job["files_scored"] += len(rows)
            job["files_failed"] += len(chunk) - len(rows)

    # Re-derive the day's events from whatever is stored now — including days where
    # nothing new was scored, so detections that were never aggregated (events lost,
    # or written before the corroboration filter) still produce their events.
    events = await rebuild_radio_burst_events(
        db, since=day_start, until=end_bound, source=BACKFILL_EVENT_SOURCE
    )
    await _suppress_notifications(db, events)
    if job is not None:
        job["events_written"] += len(events)

    covered_now = len(await filenames_in_range(db, day_start, day_end))
    fully_elapsed = end_bound >= day_end
    complete = fully_elapsed and _is_complete(covered_now, len(archive_files))
    row = await upsert_day(
        db,
        day,
        state=STATE_DONE if complete else STATE_PARTIAL,
        archive_files=len(archive_files),
        covered_files=covered_now,
        scored_files=scored,
        failed_files=failed,
        events=len(events),
        model_id=spec.id,
        error=None,
        completed_at=datetime.now(timezone.utc) if complete else None,
    )
    logger.info(
        "burst backfill %s: scored %d new file(s) (%d failed), %d/%d covered, "
        "%d event(s) — %s",
        day, scored, failed, covered_now, len(archive_files), len(events), row["state"],
    )
    return row


# ── Job control ──────────────────────────────────────────────────────────────


def _new_job(
    first: date_cls, last: date_cls, force: bool, trigger: str
) -> dict:
    spec = resolve_binary()
    return {
        "job_id": uuid4().hex,
        "status": "running",
        "trigger": trigger,
        "start_day": first.isoformat(),
        "end_day": last.isoformat(),
        "force": force,
        "model_id": spec.id,
        "model_name": spec.name,
        "days_total": 0,
        "days_done": 0,
        "current_day": None,
        "day_files_total": 0,
        "day_files_done": 0,
        "files_scored": 0,
        "files_failed": 0,
        "events_written": 0,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "finished_at": None,
        "error": None,
        "message": "planning",
    }


async def _run_job(first: date_cls, last: date_cls, force: bool) -> None:
    """Process the planned days one at a time, each in its own session.

    A session per day rather than one for the whole run: a catch-up can take hours,
    and a connection held open across all of it is a connection that goes stale.
    """
    job = _job
    assert job is not None
    try:
        async with AsyncSessionLocal() as db:
            days = await plan_days(db, first, last, force)
        job["days_total"] = len(days)
        if not days:
            job["message"] = "no gaps found"
        for day in days:
            if _cancel:
                job["message"] = "cancelled"
                break
            job["current_day"] = day.isoformat()
            job["message"] = f"scoring {day.isoformat()}"
            async with AsyncSessionLocal() as db:
                try:
                    await process_day(db, day, force=force, job=job)
                except Exception as exc:  # noqa: BLE001 - one bad day must not end the run
                    await db.rollback()
                    logger.warning("burst backfill: %s failed: %s", day, exc)
                    try:
                        await upsert_day(db, day, state=STATE_ERROR, error=str(exc)[:500])
                    except Exception:  # pragma: no cover - defensive
                        pass
                    job["error"] = f"{day.isoformat()}: {exc}"[:300]
            job["days_done"] += 1
            job["current_day"] = None
        job["status"] = "cancelled" if _cancel else "done"
        if job["status"] == "done":
            job["message"] = (
                f"filled {job['files_scored']} file(s) across {job['days_done']} day(s)"
                if job["files_scored"]
                else job["message"] or "nothing to fill"
            )
    except Exception as exc:  # noqa: BLE001 - report through the job, never crash the loop
        logger.warning("burst backfill run failed: %s", exc, exc_info=True)
        job["status"] = "error"
        job["error"] = str(exc)[:300]
        job["message"] = "failed"
    finally:
        job["finished_at"] = datetime.now(timezone.utc).isoformat()


def is_running() -> bool:
    return _task is not None and not _task.done()


def start(
    first: date_cls, last: date_cls, force: bool = False, trigger: str = "manual"
) -> dict:
    """Launch a catch-up over ``[first, last]``; returns the job snapshot.

    Raises ``BackfillBusyError`` when one is already running — two passes over the
    same days would just download everything twice.
    """
    global _job, _task, _cancel
    if is_running():
        raise BackfillBusyError("a catch-up run is already in progress")
    _cancel = False
    _job = _new_job(first, last, force, trigger)
    _task = asyncio.create_task(_run_job(first, last, force))
    logger.info(
        "burst backfill started (%s): %s → %s%s",
        trigger, first, last, " [force re-score]" if force else "",
    )
    return dict(_job)


def cancel() -> bool:
    """Ask the running job to stop after the current chunk. False if none is."""
    global _cancel
    if not is_running():
        return False
    _cancel = True
    if _job is not None:
        _job["message"] = "cancelling…"
    return True


def current_job() -> dict | None:
    """The running job, or the last one that finished (None before any run)."""
    return dict(_job) if _job is not None else None


# ── Automatic catch-up ───────────────────────────────────────────────────────


async def run_auto_catch_up() -> dict | None:
    """Fill any gap inside the automatic window. Called on startup and hourly.

    Cheap when there is nothing to do: finished days are skipped from the ledger
    without a network call, so a healthy deployment lists only today. Never
    raises — a catch-up failure must not disturb the scheduler.
    """
    if not (settings.radio_burst_enabled and settings.radio_burst_backfill_enabled):
        return None
    if is_running():
        return None
    try:
        today = datetime.now(timezone.utc).date()
        first = today - timedelta(days=max(0, settings.radio_burst_backfill_max_days - 1))
        return start(first, today, force=False, trigger="auto")
    except Exception as exc:  # noqa: BLE001
        logger.warning("automatic burst catch-up could not start: %s", exc)
        return None


# ── Coverage (for the Settings page) ─────────────────────────────────────────


async def coverage(db: AsyncSession, days: int) -> list[dict]:
    """Per-day coverage for the last ``days`` UTC days, oldest first.

    Days with no ledger row are reported as ``unknown`` rather than invented: the
    backfill has simply never looked at them (a fresh install, or a day older than
    the window), and saying so is more honest than implying a gap.
    """
    today = datetime.now(timezone.utc).date()
    first = today - timedelta(days=max(1, days) - 1)
    rows = await days_in_range(db, first, today)
    out: list[dict] = []
    day = first
    while day <= today:
        row = rows.get(day)
        out.append(
            {
                "day": day.isoformat(),
                "state": row["state"] if row else "unknown",
                "archive_files": row["archive_files"] if row else 0,
                "covered_files": row["covered_files"] if row else 0,
                "events": row["events"] if row else 0,
                "model_id": row["model_id"] if row else "",
                "error": row["error"] if row else None,
            }
        )
        day += timedelta(days=1)
    return out

