"""Offline catch-up: filling the archive days the live scanner never saw.

Inference and the archive listing are mocked — what is under test is the catch-up
logic itself: which days it decides to work on, that it scores only what is
missing, that it rebuilds the day's events without disturbing anything outside the
day, that it leaves the live scanner's window alone, and that filling an old gap
does not replay as a wave of notifications.
"""
from datetime import datetime, time, timedelta, timezone

import pytest
from httpx import ASGITransport, AsyncClient

from app.collectors.collect_ecallisto import FitsFile
from app.config import settings
from app.main import app
from app.models.radio_backfill import STATE_DONE, STATE_PARTIAL
from app.repositories.event_repo import query_range, upsert_events
from app.repositories.notification_repo import sent_severities
from app.repositories.radio_backfill_repo import get_day, upsert_day
from app.repositories.radio_detection_repo import detections_for_range, upsert_detections
from app.services.event_service import event_id_for
from app.services import radio_backfill_service as bf

# Enough stations, confident enough, to clear the corroboration filter.
_STATIONS = ["SRI-Lanka", "HUMAIN", "GLASGOW", "BIR"]
_GAP_DAY = datetime(2026, 6, 15, tzinfo=timezone.utc).date()


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


def _fits(station: str, start: datetime) -> FitsFile:
    name = f"{station}_{start:%Y%m%d_%H%M%S}_01.fit.gz"
    return FitsFile(
        station=station, start=start, filename=name, url=f"https://a/{name}", focus="01"
    )


def _day_files(day, hours=(2, 3)) -> list[FitsFile]:
    """One segment per station at each of ``hours`` on ``day``."""
    base = datetime.combine(day, time.min, tzinfo=timezone.utc)
    return [
        _fits(st, base + timedelta(hours=h))
        for h in hours
        for st in _STATIONS
    ]


def _mock_archive(monkeypatch, files: list[FitsFile]) -> None:
    async def _list_day_files(day):
        base = datetime.combine(day, time.min, tzinfo=timezone.utc)
        return [f for f in files if base <= f.start < base + timedelta(days=1)]

    monkeypatch.setattr(bf, "list_day_files", _list_day_files)


def _mock_inference(monkeypatch, probability: float = 0.95, scored=None):
    """Score every file as a burst; record which filenames were actually sent."""

    async def _predict_url(url, filename=None, *, model_id=None, classify_types=None):
        if scored is not None:
            scored.append(filename)
        return {
            "burst_probability": probability,
            "predicted_label": "Burst",
            "alert_level": "High-confidence burst",
            "model_id": model_id or "ccm-1.1.0",
            "burst_type": "Type III",
            "type_confidence": 0.8,
            "type_model_id": "ccmt-1.0.0",
        }

    import app.services.burst_inference_client as client_mod

    monkeypatch.setattr(client_mod, "predict_url", _predict_url)


# ── Planning ─────────────────────────────────────────────────────────────────


async def test_plan_skips_completed_days_but_never_today(db_session):
    today = datetime.now(timezone.utc).date()
    first = today - timedelta(days=3)
    for offset in range(4):
        await upsert_day(
            db_session,
            today - timedelta(days=offset),
            state=STATE_DONE,
            archive_files=10,
            covered_files=10,
        )

    days = await bf.plan_days(db_session, first, today)

    # Every past day is settled; today is still being published, so it is always
    # revisited (the live scan may have missed segments).
    assert days == [today]


async def test_plan_includes_gaps_newest_first(db_session):
    today = datetime.now(timezone.utc).date()
    first = today - timedelta(days=3)
    await upsert_day(db_session, today - timedelta(days=1), state=STATE_DONE)
    await upsert_day(db_session, today - timedelta(days=2), state=STATE_PARTIAL)

    days = await bf.plan_days(db_session, first, today)

    assert days == [today, today - timedelta(days=2), today - timedelta(days=3)]


async def test_force_replans_even_completed_days(db_session):
    today = datetime.now(timezone.utc).date()
    for offset in range(3):
        await upsert_day(db_session, today - timedelta(days=offset), state=STATE_DONE)

    days = await bf.plan_days(db_session, today - timedelta(days=2), today, force=True)

    assert len(days) == 3


# ── Scoring a missed day ─────────────────────────────────────────────────────


async def test_process_day_fills_gap_and_builds_events(db_session, monkeypatch):
    files = _day_files(_GAP_DAY)
    _mock_archive(monkeypatch, files)
    _mock_inference(monkeypatch)

    row = await bf.process_day(db_session, _GAP_DAY)

    stored = await detections_for_range(
        db_session,
        datetime.combine(_GAP_DAY, time.min, tzinfo=timezone.utc),
        datetime.combine(_GAP_DAY, time.min, tzinfo=timezone.utc) + timedelta(days=1),
    )
    assert len(stored) == len(files)
    assert row["state"] == STATE_DONE
    assert row["archive_files"] == len(files) == row["covered_files"]

    # Both 15-minute windows are corroborated by 4 stations -> two burst events.
    events = await query_range(
        db_session,
        datetime.combine(_GAP_DAY, time.min, tzinfo=timezone.utc),
        datetime.combine(_GAP_DAY, time.max, tzinfo=timezone.utc),
    )
    bursts = [e for e in events if e["type"] == "radio_burst"]
    assert len(bursts) == 2
    assert all(e["source"] == "ml-model-backfill" for e in bursts)
    assert row["events"] == 2


async def test_already_scored_files_are_not_rescored(db_session, monkeypatch):
    files = _day_files(_GAP_DAY)
    # Half the day was scored before the dashboard went down - by an older model.
    await upsert_detections(
        db_session,
        [
            {
                "filename": f.filename, "station": f.station, "start_time": f.start,
                "end_time": f.start + timedelta(minutes=15), "focus": f.focus,
                "probability": 0.91, "predicted_label": "Burst",
                "alert_level": "High-confidence burst", "model_id": "ccm-1.0.0",
            }
            for f in files[: len(_STATIONS)]
        ],
    )
    scored: list[str] = []
    _mock_archive(monkeypatch, files)
    _mock_inference(monkeypatch, scored=scored)

    row = await bf.process_day(db_session, _GAP_DAY)

    # A day covered by *any* model counts as covered, so only the rest is scored.
    assert sorted(scored) == sorted(f.filename for f in files[len(_STATIONS):])
    assert row["covered_files"] == len(files)


async def test_force_rescores_covered_files(db_session, monkeypatch):
    files = _day_files(_GAP_DAY, hours=(2,))
    await upsert_detections(
        db_session,
        [
            {
                "filename": f.filename, "station": f.station, "start_time": f.start,
                "end_time": f.start + timedelta(minutes=15), "focus": f.focus,
                "probability": 0.2, "predicted_label": "No_Burst",
                "alert_level": "", "model_id": "ccm-1.0.0",
            }
            for f in files
        ],
    )
    scored: list[str] = []
    _mock_archive(monkeypatch, files)
    _mock_inference(monkeypatch, scored=scored)

    await bf.process_day(db_session, _GAP_DAY, force=True)

    assert sorted(scored) == sorted(f.filename for f in files)
    stored = await detections_for_range(
        db_session,
        datetime.combine(_GAP_DAY, time.min, tzinfo=timezone.utc),
        datetime.combine(_GAP_DAY, time.min, tzinfo=timezone.utc) + timedelta(days=1),
    )
    assert all(d["predicted_label"] == "Burst" for d in stored)  # re-scored in place


async def test_live_window_is_left_to_the_scanner(db_session, monkeypatch):
    """Today's most recent hours belong to the live scan, not the catch-up."""
    now = datetime.now(timezone.utc)
    today = now.date()
    old = now - timedelta(hours=settings.radio_burst_max_age_hours + 2)
    fresh = now - timedelta(minutes=20)
    files = [_fits(st, old) for st in _STATIONS] + [_fits(st, fresh) for st in _STATIONS]
    # Only keep files that actually land on today, so a run just after midnight
    # does not turn this into an assertion about yesterday.
    files = [f for f in files if f.start.date() == today]
    scored: list[str] = []
    _mock_archive(monkeypatch, files)
    _mock_inference(monkeypatch, scored=scored)

    row = await bf.process_day(db_session, today)

    assert all(datetime.fromisoformat(_start_of(n)) < bf._live_cutoff() for n in scored)
    # Today can never be "done": its live window is deliberately not covered.
    assert row["state"] == STATE_PARTIAL


def _start_of(filename: str) -> str:
    """UTC start encoded in an e-CALLISTO filename, as an ISO string."""
    _, ymd, hms, _ = filename.split("_")
    return datetime.strptime(ymd + hms, "%Y%m%d%H%M%S").replace(
        tzinfo=timezone.utc
    ).isoformat()


async def test_day_rebuild_leaves_neighbouring_days_alone(db_session, monkeypatch):
    """A day-scoped rebuild must not delete events outside the day it re-derived."""
    neighbour = datetime.combine(
        _GAP_DAY - timedelta(days=1), time(12, 0), tzinfo=timezone.utc
    )
    await upsert_events(
        db_session,
        [{
            "type": "radio_burst", "start_time": neighbour,
            "end_time": neighbour + timedelta(minutes=15), "peak_time": neighbour,
            "peak_value": 0.9, "severity": "High-confidence burst",
            "description": "yesterday's burst", "source_url": None,
        }],
        source="ml-model",
    )
    _mock_archive(monkeypatch, _day_files(_GAP_DAY))
    _mock_inference(monkeypatch)

    await bf.process_day(db_session, _GAP_DAY)

    events = await query_range(
        db_session, neighbour - timedelta(hours=1), neighbour + timedelta(hours=1)
    )
    assert any(e["description"] == "yesterday's burst" for e in events)


# ── Silence ──────────────────────────────────────────────────────────────────


async def test_backfilled_events_are_marked_as_already_notified(
    db_session, monkeypatch
):
    """Filling a gap must not replay days of alerts to Telegram/webhooks."""
    _mock_archive(monkeypatch, _day_files(_GAP_DAY))
    _mock_inference(monkeypatch)

    await bf.process_day(db_session, _GAP_DAY)

    events = await query_range(
        db_session,
        datetime.combine(_GAP_DAY, time.min, tzinfo=timezone.utc),
        datetime.combine(_GAP_DAY, time.max, tzinfo=timezone.utc),
    )
    bursts = [e for e in events if e["type"] == "radio_burst"]
    ids = [event_id_for(e) for e in bursts]
    ledger = await sent_severities(db_session, ids)

    assert set(ledger) == set(ids)
    # At the level the dispatcher would compare against, so a later *escalation*
    # of the same window still goes out.
    assert set(ledger.values()) == {"warning"}


async def test_a_live_notification_is_not_overwritten(db_session, monkeypatch):
    """An event already announced live keeps its recorded severity."""
    from app.repositories.notification_repo import record_sent

    files = _day_files(_GAP_DAY, hours=(2,))
    window = files[0].start
    eid = event_id_for({"type": "radio_burst", "start_time": window})
    await record_sent(db_session, [(eid, "info")])
    _mock_archive(monkeypatch, files)
    _mock_inference(monkeypatch)

    await bf.process_day(db_session, _GAP_DAY)

    ledger = await sent_severities(db_session, [eid])
    assert ledger[eid] == "info"


# ── Failures and API ─────────────────────────────────────────────────────────


async def test_unscorable_files_leave_the_day_open_for_retry(db_session, monkeypatch):
    files = _day_files(_GAP_DAY)
    _mock_archive(monkeypatch, files)

    async def _failing(url, filename=None, *, model_id=None, classify_types=None):
        return None  # download or inference failed

    import app.services.burst_inference_client as client_mod

    monkeypatch.setattr(client_mod, "predict_url", _failing)

    row = await bf.process_day(db_session, _GAP_DAY)

    assert row["failed_files"] == len(files)
    assert row["covered_files"] == 0
    assert row["state"] == STATE_PARTIAL  # retried on the next pass
    assert (await get_day(db_session, _GAP_DAY))["state"] == STATE_PARTIAL


async def test_status_endpoint_reports_coverage(client, db_session):
    today = datetime.now(timezone.utc).date()
    await upsert_day(
        db_session, today - timedelta(days=1), state=STATE_DONE,
        archive_files=4800, covered_files=4800, events=3,
    )

    res = await client.get("/api/radio/backfill?days=3")

    assert res.status_code == 200
    body = res.json()
    assert body["auto_window_days"] == settings.radio_burst_backfill_max_days
    assert body["live_window_hours"] == settings.radio_burst_max_age_hours
    assert [d["day"] for d in body["coverage"]] == [
        (today - timedelta(days=n)).isoformat() for n in (2, 1, 0)
    ]
    yesterday = body["coverage"][1]
    assert yesterday["state"] == "done" and yesterday["events"] == 3
    assert body["coverage"][0]["state"] == "unknown"  # never inspected


async def test_start_endpoint_validates_the_range(client, monkeypatch):
    res = await client.post(
        "/api/radio/backfill", json={"start": "2026-06-10", "end": "2026-06-01"}
    )
    assert res.status_code == 400

    started: dict = {}

    def _start(first, last, force=False, trigger="manual"):
        started.update(first=first, last=last, force=force, trigger=trigger)
        return bf._new_job(first, last, force, trigger)

    monkeypatch.setattr(bf, "start", _start)
    res = await client.post(
        "/api/radio/backfill",
        json={"start": "2026-06-01", "end": "2026-06-03", "force": True},
    )

    assert res.status_code == 200
    assert res.json()["status"] == "running"
    assert started["first"].isoformat() == "2026-06-01"
    assert started["last"].isoformat() == "2026-06-03"
    assert started["force"] is True


async def test_cancel_without_a_run_is_a_conflict(client):
    res = await client.post("/api/radio/backfill/cancel")
    assert res.status_code == 409
