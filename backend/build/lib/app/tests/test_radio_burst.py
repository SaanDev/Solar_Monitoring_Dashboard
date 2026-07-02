"""Tests for the ML radio-burst scanner: pure 15-minute window aggregation, the
scan/dedup/persist pass (with the archive + inference service mocked), event/alert
surfacing, resilience to outages, and the per-file detections endpoint."""
from datetime import datetime, timedelta, timezone

import pytest
from httpx import ASGITransport, AsyncClient

from app.collectors.collect_ecallisto import FitsFile
from app.main import app
from app.repositories.status_repo import get_all
from app.services import radio_burst_service as rbs
from app.services.event_service import get_events, get_latest_alerts

_T0 = datetime(2026, 6, 19, 21, 37, 12, tzinfo=timezone.utc)


# ── Pure helpers ─────────────────────────────────────────────────────────────


def test_floor_to_window_snaps_to_quarter_hour():
    assert rbs._floor_to_window(_T0) == datetime(2026, 6, 19, 21, 30, tzinfo=timezone.utc)
    on_boundary = datetime(2026, 6, 19, 21, 45, tzinfo=timezone.utc)
    assert rbs._floor_to_window(on_boundary) == on_boundary


def _det(station: str, start: datetime, prob: float, level: str) -> dict:
    return {
        "filename": f"{station}_{start:%Y%m%d_%H%M%S}_01.fit.gz",
        "station": station,
        "start_time": start,
        "probability": prob,
        "alert_level": level,
    }


def test_aggregate_corroborated_window():
    # 4 stations, 2 of them p>0.9 -> qualifies; one event listing all four.
    base = datetime(2026, 6, 19, 21, 30, tzinfo=timezone.utc)
    dets = [
        _det("SRI-Lanka", base + timedelta(minutes=1), 0.97, "High-confidence burst"),
        _det("HUMAIN", base + timedelta(minutes=2), 0.92, "High-confidence burst"),
        _det("GLASGOW", base + timedelta(minutes=3), 0.70, "Likely burst"),
        _det("BIR", base + timedelta(minutes=4), 0.65, "Likely burst"),
    ]
    events = rbs.aggregate_events(dets)
    assert len(events) == 1
    ev = events[0]
    assert ev["type"] == "radio_burst"
    assert ev["start_time"] == base
    assert ev["end_time"] == base + timedelta(minutes=15)
    assert ev["peak_value"] == 0.97                       # the highest probability
    assert ev["severity"] == "High-confidence burst"      # alert level of the peak
    assert "4 stations" in ev["description"]
    assert "2 high-confidence" in ev["description"]
    for s in ("SRI-Lanka", "HUMAIN", "GLASGOW", "BIR"):
        assert s in ev["description"]


def test_aggregate_requires_corroboration():
    base = datetime(2026, 6, 19, 21, 30, tzinfo=timezone.utc)
    # Only 3 stations -> below the 4-station minimum.
    three = [_det(s, base, 0.95, "High-confidence burst") for s in ("A", "B", "C")]
    assert rbs.aggregate_events(three) == []
    # 4 stations but only 1 above p>0.9 -> below the 2 high-confidence minimum.
    low_conf = [
        _det("A", base, 0.95, "High-confidence burst"),
        _det("B", base, 0.70, "Likely burst"),
        _det("C", base, 0.65, "Likely burst"),
        _det("D", base, 0.62, "Likely burst"),
    ]
    assert rbs.aggregate_events(low_conf) == []
    # 4 stations + 2 high-confidence -> qualifies.
    ok = [
        _det("A", base, 0.95, "High-confidence burst"),
        _det("B", base, 0.93, "High-confidence burst"),
        _det("C", base, 0.65, "Likely burst"),
        _det("D", base, 0.62, "Likely burst"),
    ]
    assert len(rbs.aggregate_events(ok)) == 1


def test_aggregate_separates_distinct_windows():
    a = datetime(2026, 6, 19, 21, 30, tzinfo=timezone.utc)
    b = datetime(2026, 6, 19, 22, 0, tzinfo=timezone.utc)
    window = lambda t: [_det(s, t, 0.95, "High-confidence burst") for s in ("A", "B", "C", "D")]
    events = rbs.aggregate_events(window(a) + window(b))
    assert {e["start_time"] for e in events} == {a, b}


# ── Scan pass (archive + inference mocked) ───────────────────────────────────


def _recent_start() -> datetime:
    """A timestamp ~8 min ago, snapped to its 15-min window so a group of files
    sharing it lands in one window regardless of the wall-clock at test time."""
    now = datetime.now(timezone.utc)
    return rbs._floor_to_window(now - timedelta(minutes=8))


def _file_at(station: str, start: datetime) -> FitsFile:
    return FitsFile(
        station=station,
        start=start,
        filename=f"{station}_{start:%Y%m%d_%H%M%S}_01.fit.gz",
        url=f"https://archive/{station}_{start:%Y%m%d_%H%M%S}_01.fit.gz",
        focus="01",
    )


def _install_archive(monkeypatch, files: list[FitsFile]) -> None:
    async def _list_day_files(day):
        return [f for f in files if f.start.date() == day]

    monkeypatch.setattr(rbs, "list_day_files", _list_day_files)


def _install_inference(monkeypatch, burst_stations: set[str], counter: list[int]) -> None:
    async def _predict_url(url, filename=None):
        counter[0] += 1
        is_burst = any(s in (filename or url) for s in burst_stations)
        return {
            "predicted_label": "Burst" if is_burst else "No_Burst",
            "burst_probability": 0.96 if is_burst else 0.04,
            "alert_level": "High-confidence burst" if is_burst else "No alert",
        }

    monkeypatch.setattr(rbs, "predict_url", _predict_url)


async def test_scan_creates_burst_event_and_alert(db_session, monkeypatch):
    start = _recent_start()
    burst = ["SRI-Lanka", "HUMAIN", "GLASGOW", "BIR"]  # 4 stations (corroborated)
    files = [_file_at(s, start) for s in burst] + [_file_at("ALASKA", start)]
    _install_archive(monkeypatch, files)
    calls = [0]
    _install_inference(monkeypatch, burst_stations=set(burst), counter=calls)

    written = await rbs.scan_and_detect_radio_bursts(db_session)
    assert written == 1                       # all share one corroborated window
    assert calls[0] == 5                       # every new file scored once

    alerts = [a for a in await get_latest_alerts(db_session) if a.type == "radio_burst"]
    assert len(alerts) == 1
    assert alerts[0].severity == "warning"     # High-confidence -> warning
    for s in burst:
        assert s in alerts[0].message
    assert "ALASKA" not in alerts[0].message    # No_Burst station excluded


async def test_scan_dedupes_already_scored_files(db_session, monkeypatch):
    start = _recent_start()
    burst = ["SRI-Lanka", "HUMAIN", "GLASGOW", "BIR"]  # 4 stations -> one event
    files = [_file_at(s, start) for s in burst]
    _install_archive(monkeypatch, files)
    calls = [0]
    _install_inference(monkeypatch, burst_stations=set(burst), counter=calls)

    await rbs.scan_and_detect_radio_bursts(db_session)
    assert calls[0] == 4
    # Second pass over the same archive listing: nothing new to score.
    await rbs.scan_and_detect_radio_bursts(db_session)
    assert calls[0] == 4

    # The event remains a single window entry (idempotent upsert).
    events = [e for e in await get_events(
        db_session,
        datetime.now(timezone.utc) - timedelta(hours=2),
        datetime.now(timezone.utc) + timedelta(minutes=30),
    ) if e.type == "radio_burst"]
    assert len(events) == 1


async def test_scan_resilient_when_inference_unavailable(db_session, monkeypatch):
    files = [_file_at("SRI-Lanka", _recent_start())]
    _install_archive(monkeypatch, files)

    async def _predict_url(url, filename=None):
        return None  # service unreachable -> client returns None

    monkeypatch.setattr(rbs, "predict_url", _predict_url)

    # No exception, no events, returns gracefully.
    written = await rbs.scan_and_detect_radio_bursts(db_session)
    assert written == 0


async def test_scan_resilient_when_archive_listing_fails(db_session, monkeypatch):
    async def _list_day_files(day):
        raise RuntimeError("archive down")

    monkeypatch.setattr(rbs, "list_day_files", _list_day_files)
    monkeypatch.setattr(rbs, "predict_url", lambda *a, **k: None)

    assert await rbs.scan_and_detect_radio_bursts(db_session) == 0


# ── Health / observability (source_status) ───────────────────────────────────


async def test_scan_records_ok_status(db_session, monkeypatch):
    _install_archive(monkeypatch, [_file_at("SRI-Lanka", _recent_start())])
    _install_inference(monkeypatch, burst_stations={"SRI-Lanka"}, counter=[0])

    await rbs.scan_and_detect_radio_bursts(db_session)

    status = await get_all(db_session)
    assert rbs.SOURCE_NAME in status
    assert status[rbs.SOURCE_NAME].status == "ok"


async def test_scan_reports_inference_unreachable(db_session, monkeypatch):
    # Files exist to score, but the inference client returns None for all of them
    # (microservice down) — the scan must surface this, not fail silently.
    _install_archive(
        monkeypatch, [_file_at("SRI-Lanka", _recent_start()), _file_at("HUMAIN", _recent_start())]
    )

    async def _down(url, filename=None):
        return None

    monkeypatch.setattr(rbs, "predict_url", _down)

    await rbs.scan_and_detect_radio_bursts(db_session)

    status = await get_all(db_session)
    assert status[rbs.SOURCE_NAME].status == "error"
    assert "inference service unreachable" in (status[rbs.SOURCE_NAME].last_error or "")


async def test_scan_reports_archive_unreachable(db_session, monkeypatch):
    async def _list_day_files(day):
        raise RuntimeError("archive down")

    monkeypatch.setattr(rbs, "list_day_files", _list_day_files)
    await rbs.scan_and_detect_radio_bursts(db_session)

    status = await get_all(db_session)
    assert status[rbs.SOURCE_NAME].status == "error"
    assert "archive unreachable" in (status[rbs.SOURCE_NAME].last_error or "")


# ── Detections endpoint ──────────────────────────────────────────────────────


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


async def test_detections_endpoint(client, db_session, monkeypatch):
    start = _recent_start()
    files = [_file_at("SRI-Lanka", start), _file_at("GLASGOW", start)]
    _install_archive(monkeypatch, files)
    _install_inference(monkeypatch, burst_stations={"SRI-Lanka"}, counter=[0])
    await rbs.scan_and_detect_radio_bursts(db_session)

    # Query by the files' own UTC date (robust across the midnight boundary).
    r = await client.get(f"/api/radio/bursts/detections?date={start.date().isoformat()}")
    assert r.status_code == 200
    body = r.json()
    assert body["count"] == 2
    assert body["burst_count"] == 1
    labels = {d["station"]: d["predicted_label"] for d in body["detections"]}
    assert labels["SRI-Lanka"] == "Burst"
    assert labels["GLASGOW"] == "No_Burst"


# ── Corroboration cleanup + stored-detections endpoint ───────────────────────


async def test_rebuild_drops_non_qualifying_events(db_session):
    from app.repositories.event_repo import query_range, upsert_events
    from app.repositories.radio_detection_repo import upsert_detections

    now = datetime.now(timezone.utc)
    window = rbs._floor_to_window(now - timedelta(minutes=30))
    # A radio_burst event left over from before the corroboration filter existed.
    await upsert_events(
        db_session,
        [{
            "type": "radio_burst", "start_time": window,
            "end_time": window + timedelta(minutes=15), "peak_time": window,
            "peak_value": 0.9, "severity": "High-confidence burst",
            "description": "legacy event", "source_url": None,
        }],
        source="ml-model",
    )
    # That window now only has 2 burst stations -> fails the >=4 filter.
    await upsert_detections(
        db_session,
        [{
            "filename": f"S{i}_x.fit.gz", "station": f"S{i}",
            "start_time": window + timedelta(minutes=i),
            "end_time": window + timedelta(minutes=15), "focus": "01",
            "probability": 0.95, "predicted_label": "Burst",
            "alert_level": "High-confidence burst",
        } for i in range(2)],
    )

    await rbs.rebuild_radio_burst_events(db_session)

    rows = await query_range(db_session, window - timedelta(hours=1), now + timedelta(minutes=30))
    assert not any(r["type"] == "radio_burst" for r in rows)  # cleaned out


async def test_stored_endpoint_assembles_from_db(client, db_session, monkeypatch):
    from app.repositories.radio_detection_repo import upsert_detections
    from app.schemas.radio_schema import BurstEventsResponse
    from app.services import burst_predictor_service as bps

    day = datetime(2026, 6, 15, tzinfo=timezone.utc)
    rows = [
        {
            "filename": f"{st}_x.fit.gz", "station": st,
            "start_time": day.replace(hour=2, minute=i),
            "end_time": day.replace(hour=2, minute=i), "focus": "01",
            "probability": 0.97, "predicted_label": "Burst",
            "alert_level": "High-confidence burst",
        }
        # 4 stations (>=2 high-confidence) so the cluster is corroborated.
        for i, st in enumerate(["SRI-Lanka", "HUMAIN", "GLASGOW", "BIR"])
    ]
    await upsert_detections(db_session, rows)

    async def _official(d):
        return BurstEventsResponse(date="2026-06-15", count=0, sri_lanka_count=0, events=[])

    monkeypatch.setattr(bps, "get_burst_events_for_date", _official)

    r = await client.get("/api/radio/predict/stored?date=2026-06-15")
    assert r.status_code == 200
    body = r.json()
    assert body["date"] == "2026-06-15"
    assert body["total_files"] == 4
    assert body["burst_count"] == 4
    assert body["event_count"] == 1  # the four cluster into one corroborated window
