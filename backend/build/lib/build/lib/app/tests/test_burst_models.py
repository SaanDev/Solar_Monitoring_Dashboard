"""Model selection and burst typing end to end through the services and API.

Inference itself is mocked (it is covered by test_ml_checkpoints.py); what matters
here is that the chosen model reaches the scorer, that its identity and any burst
type survive into the database, the events feed and the API responses, and that
switching the configured model re-scores rather than silently keeping the previous
model's verdicts.
"""
import asyncio
from datetime import datetime, timedelta, timezone

import pytest
from httpx import ASGITransport, AsyncClient

from app.collectors.collect_ecallisto import FitsFile
from app.config import settings
from app.main import app
from app.repositories.radio_detection_repo import detections_for_range
from app.services import burst_predictor_service as bps
from app.services import radio_burst_service as rbs
from app.services.event_service import get_latest_alerts

_D = datetime(2026, 6, 15, tzinfo=timezone.utc).date()
_CORROBORATING = ["SRI-Lanka", "HUMAIN", "GLASGOW", "BIR"]


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


def _fits(station: str, start: datetime) -> FitsFile:
    name = f"{station}_{start:%Y%m%d_%H%M%S}_01.fit.gz"
    return FitsFile(station=station, start=start, filename=name, url=f"https://a/{name}", focus="01")


async def _empty_official(day):
    from app.schemas.radio_schema import BurstEventsResponse

    return BurstEventsResponse(date=day.isoformat(), count=0, events=[])


def _burst_record(model_id: str, burst_type: str | None = None, probability: float = 0.95) -> dict:
    """What predict_bytes returns for a burst, shaped like the real record."""
    record = {
        "predicted_label": "Burst",
        "burst_probability": probability,
        "alert_level": "High-confidence burst",
        "model_id": model_id,
        "model_name": "CCM v1.1.0" if model_id == "ccm-1.1.0" else "CCM v1.0.0",
    }
    if burst_type:
        record.update(
            burst_type=burst_type,
            type_confidence=0.82,
            type_model_id="ccmt-1.0.0",
            type_regions=[
                {
                    "freq_min_mhz": 26.5, "freq_max_mhz": 44.6,
                    "start_seconds": 93, "end_seconds": 163,
                    "burst_type": burst_type, "confidence": 0.82, "area": 7657,
                }
            ],
        )
    return record


async def _drain(job_id: str) -> dict:
    for _ in range(200):
        if bps.get_job(job_id)["status"] != "running":
            break
        await asyncio.sleep(0.02)
    return bps.get_job(job_id)


# ── On-demand runs ────────────────────────────────────────────────────────────


async def test_selected_model_reaches_the_scorer_and_the_result(monkeypatch):
    seen: list[str | None] = []

    async def _list_day_files(day):
        return [_fits(s, datetime(2026, 6, 15, 2, 0, tzinfo=timezone.utc)) for s in _CORROBORATING]

    async def _predict_url(url, filename=None, *, model_id=None, classify_types=None):
        seen.append(model_id)
        return _burst_record(model_id or "ccm-1.1.0")

    monkeypatch.setattr(bps, "list_day_files", _list_day_files)
    monkeypatch.setattr(bps, "predict_url", _predict_url)
    monkeypatch.setattr(bps, "get_burst_events_for_date", _empty_official)

    job = await _drain(bps.start_prediction(_D, [], model_id="ccm-1.0.0"))
    assert job["status"] == "done"
    assert set(seen) == {"ccm-1.0.0"}          # every file scored with the choice
    assert job["model_id"] == "ccm-1.0.0"

    result = await bps.assemble_result(job["rows"], _D, model_id=job["model_id"])
    assert result["model_id"] == "ccm-1.0.0"
    assert result["model_name"] == "CCM v1.0.0"


async def test_job_records_the_type_toggle_and_passes_it_through(monkeypatch):
    seen: list[bool | None] = []

    async def _list_day_files(day):
        return [_fits("BIR", datetime(2026, 6, 15, 2, 0, tzinfo=timezone.utc))]

    async def _predict_url(url, filename=None, *, model_id=None, classify_types=None):
        seen.append(classify_types)
        return _burst_record("ccm-1.1.0")

    monkeypatch.setattr(bps, "list_day_files", _list_day_files)
    monkeypatch.setattr(bps, "predict_url", _predict_url)

    job = await _drain(bps.start_prediction(_D, [], classify_types=False))
    assert job["classify_types"] is False
    assert seen == [False]


async def test_burst_types_surface_on_events_and_detections(monkeypatch):
    start = datetime(2026, 6, 15, 2, 0, tzinfo=timezone.utc)

    async def _list_day_files(day):
        return [_fits(s, start) for s in _CORROBORATING]

    async def _predict_url(url, filename=None, *, model_id=None, classify_types=None):
        # Three stations see Type III, one sees Type II — a real disagreement.
        burst_type = "Type II" if "BIR" in (filename or "") else "Type III"
        return _burst_record("ccm-1.1.0", burst_type=burst_type)

    monkeypatch.setattr(bps, "list_day_files", _list_day_files)
    monkeypatch.setattr(bps, "predict_url", _predict_url)
    monkeypatch.setattr(bps, "get_burst_events_for_date", _empty_official)

    job = await _drain(bps.start_prediction(_D, [], classify_types=True))
    result = await bps.assemble_result(
        job["rows"], _D, model_id=job["model_id"], classify_types=True
    )

    assert result["classify_types"] is True
    assert result["type_model_id"] == "ccmt-1.0.0"
    assert result["type_counts"] == {"Type III": 3, "Type II": 1}

    event = result["events"][0]
    assert event["dominant_type"] in {"Type II", "Type III"}
    # The disagreement is preserved rather than flattened, so the UI can show it.
    assert event["type_counts"] == {"Type III": 3, "Type II": 1}
    detection = event["detections"][0]
    assert detection["burst_type"] in {"Type II", "Type III"}
    assert detection["regions"][0]["freq_min_mhz"] == pytest.approx(26.5)


async def test_typing_off_leaves_every_type_field_empty(monkeypatch):
    start = datetime(2026, 6, 15, 2, 0, tzinfo=timezone.utc)

    async def _list_day_files(day):
        return [_fits(s, start) for s in _CORROBORATING]

    async def _predict_url(url, filename=None, *, model_id=None, classify_types=None):
        return _burst_record("ccm-1.1.0")  # no type fields

    monkeypatch.setattr(bps, "list_day_files", _list_day_files)
    monkeypatch.setattr(bps, "predict_url", _predict_url)
    monkeypatch.setattr(bps, "get_burst_events_for_date", _empty_official)

    job = await _drain(bps.start_prediction(_D, [], classify_types=False))
    result = await bps.assemble_result(
        job["rows"], _D, model_id=job["model_id"], classify_types=False
    )
    assert result["type_counts"] == {}
    assert result["type_model_id"] is None
    assert result["events"][0]["dominant_type"] is None
    assert result["events"][0]["detections"][0]["burst_type"] is None


async def test_criteria_mode_uses_the_models_own_threshold(monkeypatch):
    """A probability between the two models' thresholds must count for the model
    whose threshold it clears, and not for the other."""
    monkeypatch.setattr(settings, "radio_burst_alert_min_probability", 0.0)
    start = datetime(2026, 6, 15, 2, 0, tzinfo=timezone.utc)
    # 0.55 is above CCM v1.1.0's 0.51 but below CCM v1.0.0's 0.595.
    rows = [
        {
            "filename": f"{s}_x.fit.gz", "station": s, "start_time": start, "focus": "01",
            "probability": 0.55, "predicted_label": "Burst",
            "alert_level": "Possible burst", "model_id": "ccm-1.1.0",
        }
        for s in _CORROBORATING
    ]
    monkeypatch.setattr(bps, "get_burst_events_for_date", _empty_official)

    lenient = await bps.assemble_result(rows, _D, model_id="ccm-1.1.0")
    assert lenient["burst_count"] == 4

    strict = await bps.assemble_result(rows, _D, model_id="ccm-1.0.0")
    assert strict["burst_count"] == 0


async def test_mixed_model_day_gates_each_row_by_its_own_threshold(monkeypatch):
    """A stored day can span two models, because switching the configured scan
    model only re-scores the recent window. Gating the whole day by one model's
    threshold would drop genuine detections from the other."""
    monkeypatch.setattr(settings, "radio_burst_alert_min_probability", 0.0)
    monkeypatch.setattr(bps, "get_burst_events_for_date", _empty_official)
    early = datetime(2026, 6, 15, 1, 0, tzinfo=timezone.utc)
    late = datetime(2026, 6, 15, 2, 0, tzinfo=timezone.utc)

    def _row(station, start, probability, model_id):
        return {
            "filename": f"{station}_{start:%H%M}.fit.gz", "station": station,
            "start_time": start, "focus": "01", "probability": probability,
            "predicted_label": "Burst", "alert_level": "Possible burst",
            "model_id": model_id,
        }

    rows = (
        # Older window, CCM v1.0.0: 0.62 clears its 0.595 threshold.
        [_row(s, early, 0.62, "ccm-1.0.0") for s in _CORROBORATING]
        # Recent window, CCM v1.1.0: 0.55 clears its 0.51 but not v1.0.0's 0.595.
        + [_row(s, late, 0.55, "ccm-1.1.0") for s in _CORROBORATING]
    )

    # Both windows survive: each row was judged by the model that produced it.
    result = await bps.assemble_result(rows, _D)
    assert result["burst_count"] == 8

    # Contrast: forcing the whole day through CCM v1.0.0's stricter threshold drops
    # the four v1.1.0 rows — the behaviour the per-row gate exists to avoid.
    forced = await bps.assemble_result(rows, _D, model_id="ccm-1.0.0")
    assert forced["burst_count"] == 4

    # Attribution is by majority, not by whichever row happened to sort first.
    rows.append(_row("EXTRA", late, 0.55, "ccm-1.1.0"))
    assert (await bps.assemble_result(rows, _D))["model_id"] == "ccm-1.1.0"


async def test_unknown_stored_model_id_still_yields_a_result(monkeypatch):
    # A row written by a model that was later retired must not 500 the endpoint.
    monkeypatch.setattr(bps, "get_burst_events_for_date", _empty_official)
    monkeypatch.setattr(settings, "radio_burst_alert_min_probability", 0.0)
    start = datetime(2026, 6, 15, 2, 0, tzinfo=timezone.utc)
    rows = [
        {
            "filename": f"{s}_x.fit.gz", "station": s, "start_time": start, "focus": "01",
            "probability": 0.99, "predicted_label": "Burst",
            "alert_level": "High-confidence burst", "model_id": "ccm-0.9.0",
        }
        for s in _CORROBORATING
    ]
    result = await bps.assemble_result(rows, _D)
    assert result["burst_count"] == 4


async def test_stored_result_infers_the_model_from_the_rows(monkeypatch):
    start = datetime(2026, 6, 15, 2, 0, tzinfo=timezone.utc)
    rows = [
        {
            "filename": f"{s}_x.fit.gz", "station": s, "start_time": start, "focus": "01",
            "probability": 0.97, "predicted_label": "Burst",
            "alert_level": "High-confidence burst", "model_id": "ccm-1.0.0",
        }
        for s in _CORROBORATING
    ]
    monkeypatch.setattr(bps, "get_burst_events_for_date", _empty_official)

    # No model_id argument: a day scanned by an older model is still attributed
    # to it, so it is scored against that model's threshold.
    result = await bps.assemble_result(rows, _D)
    assert result["model_id"] == "ccm-1.0.0"


# ── Automatic scan ────────────────────────────────────────────────────────────


def _recent(minutes_ago: int = 8) -> datetime:
    return rbs._floor_to_window(datetime.now(timezone.utc) - timedelta(minutes=minutes_ago))


def _install_scan(monkeypatch, files, record_for):
    async def _list_day_files(day):
        return [f for f in files if f.start.date() == day]

    async def _predict_url(url, filename=None, *, model_id=None, classify_types=None):
        return record_for(filename or url, model_id)

    monkeypatch.setattr(rbs, "list_day_files", _list_day_files)
    monkeypatch.setattr(rbs, "predict_url", _predict_url)


async def test_scan_persists_the_model_and_burst_type(db_session, monkeypatch):
    monkeypatch.setattr(settings, "radio_burst_binary_model", "ccm-1.1.0")
    monkeypatch.setattr(settings, "radio_burst_alert_min_probability", 0.0)
    start = _recent()
    files = [_fits(s, start) for s in _CORROBORATING]
    _install_scan(
        monkeypatch, files,
        lambda name, model_id: _burst_record(model_id or "", burst_type="Type III"),
    )

    written = await rbs.scan_and_detect_radio_bursts(db_session)
    assert written == 1

    rows = await detections_for_range(
        db_session, start - timedelta(hours=1), start + timedelta(hours=1)
    )
    assert len(rows) == 4
    assert {r["model_id"] for r in rows} == {"ccm-1.1.0"}
    assert {r["burst_type"] for r in rows} == {"Type III"}
    assert {r["type_model_id"] for r in rows} == {"ccmt-1.0.0"}

    # The alert says which model found it and what type it was — events has no
    # model column, so the description is where that provenance lives.
    alerts = [a for a in await get_latest_alerts(db_session) if a.type == "radio_burst"]
    assert len(alerts) == 1
    assert "Type III" in alerts[0].message
    assert "CCM v1.1.0" in alerts[0].message


async def test_changing_the_configured_model_rescores_the_window(db_session, monkeypatch):
    """Dedup is per model, so a switch refreshes recent verdicts instead of
    leaving the previous model's rows in place untouched."""
    monkeypatch.setattr(settings, "radio_burst_alert_min_probability", 0.0)
    start = _recent()
    files = [_fits(s, start) for s in _CORROBORATING]
    _install_scan(monkeypatch, files, lambda name, model_id: _burst_record(model_id or ""))

    monkeypatch.setattr(settings, "radio_burst_binary_model", "ccm-1.0.0")
    await rbs.scan_and_detect_radio_bursts(db_session)
    rows = await detections_for_range(
        db_session, start - timedelta(hours=1), start + timedelta(hours=1)
    )
    assert {r["model_id"] for r in rows} == {"ccm-1.0.0"}

    monkeypatch.setattr(settings, "radio_burst_binary_model", "ccm-1.1.0")
    await rbs.scan_and_detect_radio_bursts(db_session)
    rows = await detections_for_range(
        db_session, start - timedelta(hours=1), start + timedelta(hours=1)
    )
    # Replaced in place (filename is the PK), not duplicated.
    assert len(rows) == 4
    assert {r["model_id"] for r in rows} == {"ccm-1.1.0"}


async def test_repeat_scan_with_the_same_model_still_dedupes(db_session, monkeypatch):
    monkeypatch.setattr(settings, "radio_burst_binary_model", "ccm-1.1.0")
    monkeypatch.setattr(settings, "radio_burst_alert_min_probability", 0.0)
    start = _recent()
    files = [_fits(s, start) for s in _CORROBORATING]
    calls = [0]

    def _record(name, model_id):
        calls[0] += 1
        return _burst_record(model_id or "")

    _install_scan(monkeypatch, files, _record)

    await rbs.scan_and_detect_radio_bursts(db_session)
    assert calls[0] == 4
    await rbs.scan_and_detect_radio_bursts(db_session)
    assert calls[0] == 4  # nothing re-downloaded or re-scored


async def test_burst_type_reaches_the_events_api_for_the_timeline(db_session, monkeypatch, client):
    """The Timeline colors the model lane from a structured field, not by parsing
    the description prose, so burst_type has to survive all the way to /api/events."""
    monkeypatch.setattr(settings, "radio_burst_binary_model", "ccm-1.1.0")
    monkeypatch.setattr(settings, "radio_burst_alert_min_probability", 0.0)
    start = _recent()
    files = [_fits(s, start) for s in _CORROBORATING]
    _install_scan(
        monkeypatch, files,
        lambda name, model_id: _burst_record(model_id or "", burst_type="Type II"),
    )
    assert await rbs.scan_and_detect_radio_bursts(db_session) == 1

    window_start = (start - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
    window_end = (start + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
    events = (await client.get(f"/api/events?start={window_start}&end={window_end}")).json()
    bursts = [e for e in events if e["type"] == "radio_burst"]
    assert len(bursts) == 1
    assert bursts[0]["burst_type"] == "Type II"
    # severity still carries the alert level — the two must not be conflated,
    # since the timeline reads one for color and the other for the tooltip.
    assert bursts[0]["severity"] == "High-confidence burst"


async def test_untyped_burst_leaves_the_event_type_null(db_session, monkeypatch, client):
    """An untyped burst must stay null rather than defaulting to a class — the
    Timeline renders those in the lane's neutral color."""
    monkeypatch.setattr(settings, "radio_burst_binary_model", "ccm-1.1.0")
    monkeypatch.setattr(settings, "radio_burst_alert_min_probability", 0.0)
    start = _recent()
    files = [_fits(s, start) for s in _CORROBORATING]
    _install_scan(monkeypatch, files, lambda name, model_id: _burst_record(model_id or ""))
    assert await rbs.scan_and_detect_radio_bursts(db_session) == 1

    window_start = (start - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
    window_end = (start + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
    events = (await client.get(f"/api/events?start={window_start}&end={window_end}")).json()
    bursts = [e for e in events if e["type"] == "radio_burst"]
    assert len(bursts) == 1
    assert bursts[0]["burst_type"] is None


def test_aggregated_event_carries_the_window_type():
    start = datetime(2026, 6, 15, 2, 3, tzinfo=timezone.utc)
    detections = [
        {
            "station": s, "start_time": start, "probability": 0.97,
            "alert_level": "High-confidence burst",
            "burst_type": "Type III", "type_confidence": 0.9,
        }
        for s in _CORROBORATING
    ]
    events = rbs.aggregate_events(detections, model_name="CCM v1.1.0")
    assert len(events) == 1
    assert events[0]["burst_type"] == "Type III"
    assert "Type III" in events[0]["description"]


def test_window_type_comes_from_the_most_confident_detection():
    start = datetime(2026, 6, 15, 2, 0, tzinfo=timezone.utc)

    def _row(station: str, burst_type: str, confidence: float) -> dict:
        return {
            "station": station, "start_time": start, "probability": 0.95,
            "alert_level": "High-confidence burst",
            "burst_type": burst_type, "type_confidence": confidence,
        }

    # Three quiet-ish views of Type III, one much clearer view of Type II.
    items = [_row(s, "Type III", 0.41) for s in ("A", "B", "C")]
    items.append(_row("D", "Type II", 0.94))
    assert rbs._window_burst_type(items) == "Type II"
    # Untyped detections do not vote.
    assert rbs._window_burst_type([{"burst_type": None, "probability": 0.9}]) is None


# ── API ───────────────────────────────────────────────────────────────────────


async def test_models_endpoint_advertises_all_three(client):
    resp = await client.get("/api/radio/models")
    assert resp.status_code == 200
    body = resp.json()

    by_id = {m["id"]: m for m in body["models"]}
    assert set(by_id) == {"ccm-1.0.0", "ccm-1.1.0", "ccmt-1.0.0"}
    assert by_id["ccm-1.1.0"]["threshold"] == pytest.approx(0.51)
    assert by_id["ccm-1.0.0"]["threshold"] == pytest.approx(0.595)
    # A type model has no single decision threshold to report.
    assert by_id["ccmt-1.0.0"]["threshold"] is None
    assert by_id["ccmt-1.0.0"]["classes"] == ["Type II", "Type III", "Other"]
    assert body["default_binary"] in {"ccm-1.0.0", "ccm-1.1.0"}
    assert body["type_model"] == "ccmt-1.0.0"


async def test_models_endpoint_reports_default_from_configuration(client, monkeypatch):
    monkeypatch.setattr(settings, "radio_burst_binary_model", "ccm-1.0.0")
    monkeypatch.setattr(settings, "radio_burst_classify_types", False)
    body = (await client.get("/api/radio/models")).json()
    assert body["default_binary"] == "ccm-1.0.0"
    assert body["classify_types"] is False
    assert next(m for m in body["models"] if m["id"] == "ccm-1.0.0")["is_default"] is True
    assert next(m for m in body["models"] if m["id"] == "ccm-1.1.0")["is_default"] is False


async def test_predict_rejects_an_unknown_model(client):
    resp = await client.post(
        "/api/radio/predict",
        json={"date": _D.isoformat(), "stations": [], "model": "ccm-9.9.9"},
    )
    assert resp.status_code == 400
    assert "unknown model" in resp.json()["detail"]


async def test_predict_rejects_the_type_model_as_a_binary_choice(client):
    resp = await client.post(
        "/api/radio/predict",
        json={"date": _D.isoformat(), "stations": [], "model": "ccmt-1.0.0"},
    )
    assert resp.status_code == 400


async def test_predict_route_echoes_the_chosen_model(client, monkeypatch):
    async def _list_day_files(day):
        return []

    monkeypatch.setattr(bps, "list_day_files", _list_day_files)
    resp = await client.post(
        "/api/radio/predict",
        json={
            "date": _D.isoformat(), "stations": [],
            "model": "ccm-1.0.0", "classify_types": True,
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["model_id"] == "ccm-1.0.0"
    assert body["classify_types"] is True


async def test_detections_endpoint_exposes_model_and_type(client, db_session, monkeypatch):
    from app.repositories.radio_detection_repo import upsert_detections

    start = datetime(2026, 6, 15, 2, 0, tzinfo=timezone.utc)
    await upsert_detections(
        db_session,
        [
            {
                "filename": "BIR_20260615_020000_01.fit.gz", "station": "BIR",
                "start_time": start, "end_time": start + timedelta(minutes=15),
                "focus": "01", "probability": 0.97, "predicted_label": "Burst",
                "alert_level": "High-confidence burst", "model_id": "ccm-1.1.0",
                "burst_type": "Type II", "type_confidence": 0.71,
                "type_model_id": "ccmt-1.0.0",
            }
        ],
    )
    body = (await client.get("/api/radio/bursts/detections?date=2026-06-15")).json()
    assert body["count"] == 1
    detection = body["detections"][0]
    assert detection["model_id"] == "ccm-1.1.0"
    assert detection["burst_type"] == "Type II"
    assert detection["type_confidence"] == pytest.approx(0.71)
