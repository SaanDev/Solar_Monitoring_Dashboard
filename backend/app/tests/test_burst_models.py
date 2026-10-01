"""The burst model end to end through the services and API.

Inference itself is mocked (it is covered by test_ml_preprocessing.py and
test_ml_checkpoints.py); what matters here is that the chosen model reaches the
scorer, that its identity survives into the database, the events feed and the
API responses, and that detections left behind by the retired models are still
judged by their own thresholds until they are re-scored.

BnB v1.0 does not type bursts, but rows CCM v2.0 stored carry a type until they
are re-scored, and a typing model may return, so the burst-type plumbing is
still exercised with typed records.
"""
import asyncio
from datetime import datetime, timedelta, timezone

import pytest
from httpx import ASGITransport, AsyncClient

from app.collectors.collect_ecallisto import FitsFile
from app.config import settings
from app.main import app
from app.repositories.radio_detection_repo import detections_for_range, upsert_detections
from app.services import burst_predictor_service as bps
from app.services import radio_burst_service as rbs
from app.services.event_service import get_latest_alerts

_D = datetime(2026, 6, 15, tzinfo=timezone.utc).date()
_CORROBORATING = ["SRI-Lanka", "HUMAIN", "GLASGOW", "BIR"]
_MODEL = "bnb-1.0.0"


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


@pytest.fixture(autouse=True)
def _no_alert_override(monkeypatch):
    monkeypatch.setattr(settings, "radio_burst_alert_min_probability", 0.0)


def _fits(station: str, start: datetime) -> FitsFile:
    name = f"{station}_{start:%Y%m%d_%H%M%S}_01.fit.gz"
    return FitsFile(station=station, start=start, filename=name, url=f"https://a/{name}", focus="01")


async def _empty_official(day):
    from app.schemas.radio_schema import BurstEventsResponse

    return BurstEventsResponse(date=day.isoformat(), count=0, events=[])


def _burst_record(burst_type: str | None = None, probability: float = 0.95) -> dict:
    """What predict_bytes returns for a burst, shaped like the real record.

    Untyped by default, as BnB v1.0's are; a type adds what a typing model's
    record carries.
    """
    record = {
        "predicted_label": "Burst",
        "burst_probability": probability,
        "alert_level": "High-confidence burst",
        "model_id": _MODEL,
        "model_name": "BnB v1.0",
    }
    if burst_type:
        record.update(
            burst_type=burst_type,
            type_confidence=0.82,
            type_model_id=_MODEL,
            type_regions=[
                {
                    "freq_min_mhz": 26.5, "freq_max_mhz": 44.6,
                    "start_seconds": 93, "end_seconds": 163,
                    "burst_type": burst_type, "confidence": 0.82, "area": 7657,
                }
            ],
        )
    return record


def _stored(station: str, start: datetime, probability: float, model_id: str) -> dict:
    return {
        "filename": f"{station}_{start:%Y%m%d_%H%M%S}_01.fit.gz", "station": station,
        "start_time": start, "end_time": start + timedelta(minutes=15), "focus": "01",
        "probability": probability, "predicted_label": "Burst",
        "alert_level": "Possible burst", "model_id": model_id,
    }


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

    async def _predict_url(url, filename=None, *, model_id=None):
        seen.append(model_id)
        return _burst_record()

    monkeypatch.setattr(bps, "list_day_files", _list_day_files)
    monkeypatch.setattr(bps, "predict_url", _predict_url)
    monkeypatch.setattr(bps, "get_burst_events_for_date", _empty_official)

    job = await _drain(bps.start_prediction(_D, [], model_id=_MODEL))
    assert job["status"] == "done"
    assert set(seen) == {_MODEL}          # every file scored with the choice
    assert job["model_id"] == _MODEL

    result = await bps.assemble_result(job["rows"], _D, model_id=job["model_id"])
    assert result["model_id"] == _MODEL
    assert result["model_name"] == "BnB v1.0"
    # An untyped model leaves the type summary empty rather than inventing one.
    assert result["type_counts"] == {}
    assert result["events"][0]["dominant_type"] is None


async def test_burst_types_surface_on_events_and_detections(monkeypatch):
    start = datetime(2026, 6, 15, 2, 0, tzinfo=timezone.utc)

    async def _list_day_files(day):
        return [_fits(s, start) for s in _CORROBORATING]

    async def _predict_url(url, filename=None, *, model_id=None):
        # Three stations see Type III, one sees Type II — a real disagreement.
        return _burst_record("Type II" if "BIR" in (filename or "") else "Type III")

    monkeypatch.setattr(bps, "list_day_files", _list_day_files)
    monkeypatch.setattr(bps, "predict_url", _predict_url)
    monkeypatch.setattr(bps, "get_burst_events_for_date", _empty_official)

    job = await _drain(bps.start_prediction(_D, []))
    result = await bps.assemble_result(job["rows"], _D, model_id=job["model_id"])

    assert result["type_counts"] == {"Type III": 3, "Type II": 1}
    event = result["events"][0]
    assert event["dominant_type"] in {"Type II", "Type III"}
    # The disagreement is preserved rather than flattened, so the UI can show it.
    assert event["type_counts"] == {"Type III": 3, "Type II": 1}
    detection = event["detections"][0]
    assert detection["burst_type"] in {"Type II", "Type III"}
    assert detection["regions"][0]["freq_min_mhz"] == pytest.approx(26.5)


async def test_criteria_mode_uses_the_models_tuned_threshold(monkeypatch):
    """A probability below BnB v1.0's 0.56 is not an alert-grade detection."""
    monkeypatch.setattr(bps, "get_burst_events_for_date", _empty_official)
    start = datetime(2026, 6, 15, 2, 0, tzinfo=timezone.utc)
    strong = [_stored(s, start, 0.93, _MODEL) for s in _CORROBORATING]
    weak = [_stored(s, start, 0.50, _MODEL) for s in _CORROBORATING]

    assert (await bps.assemble_result(strong, _D, model_id=_MODEL))["burst_count"] == 4
    assert (await bps.assemble_result(weak, _D, model_id=_MODEL))["burst_count"] == 0
    # Raw mode takes the model's own Burst label as-is.
    assert (await bps.assemble_result(weak, _D, raw=True, model_id=_MODEL))["burst_count"] == 4


async def test_a_retired_models_rows_are_gated_by_its_own_threshold(monkeypatch):
    """A stored day can mix BnB v1.0 with rows a retired model left behind (the
    backfill re-scores them over time). Judging those by BnB v1.0's 0.56 would
    count CCM v2.0.1 evidence its own 0.80 rejected."""
    monkeypatch.setattr(bps, "get_burst_events_for_date", _empty_official)
    early = datetime(2026, 6, 15, 1, 0, tzinfo=timezone.utc)
    late = datetime(2026, 6, 15, 2, 0, tzinfo=timezone.utc)
    rows = (
        [_stored(s, early, 0.70, "ccm-2.0.1") for s in _CORROBORATING]
        + [_stored(s, late, 0.70, _MODEL) for s in _CORROBORATING]
    )

    result = await bps.assemble_result(rows, _D)
    # 0.70 clears BnB v1.0's 0.56; the same value is under CCM v2.0.1's 0.80.
    assert result["burst_count"] == 4

    # Attribution is by majority, and a retired model keeps its display name.
    rows.append(_stored("EXTRA", early, 0.70, "ccm-2.0.1"))
    result = await bps.assemble_result(rows, _D)
    assert result["model_id"] == "ccm-2.0.1"
    assert result["model_name"] == "CCM v2.0.1"


async def test_unknown_stored_model_id_still_yields_a_result(monkeypatch):
    # A row written by a model the registry has never heard of must not 500 the
    # endpoint; it is judged by the active model.
    monkeypatch.setattr(bps, "get_burst_events_for_date", _empty_official)
    start = datetime(2026, 6, 15, 2, 0, tzinfo=timezone.utc)
    rows = [_stored(s, start, 0.99, "ccm-0.9.0") for s in _CORROBORATING]
    result = await bps.assemble_result(rows, _D)
    assert result["burst_count"] == 4
    assert result["model_name"] == "ccm-0.9.0"


# ── Automatic scan ────────────────────────────────────────────────────────────


def _recent(minutes_ago: int = 8) -> datetime:
    return rbs._floor_to_window(datetime.now(timezone.utc) - timedelta(minutes=minutes_ago))


def _install_scan(monkeypatch, files, record_for):
    async def _list_day_files(day):
        return [f for f in files if f.start.date() == day]

    async def _predict_url(url, filename=None, *, model_id=None):
        return record_for(filename or url, model_id)

    monkeypatch.setattr(rbs, "list_day_files", _list_day_files)
    monkeypatch.setattr(rbs, "predict_url", _predict_url)


async def test_scan_persists_the_model(db_session, monkeypatch):
    start = _recent()
    files = [_fits(s, start) for s in _CORROBORATING]
    _install_scan(monkeypatch, files, lambda name, model_id: _burst_record())

    written = await rbs.scan_and_detect_radio_bursts(db_session)
    assert written == 1

    rows = await detections_for_range(
        db_session, start - timedelta(hours=1), start + timedelta(hours=1)
    )
    assert len(rows) == 4
    assert {r["model_id"] for r in rows} == {_MODEL}
    assert {r["burst_type"] for r in rows} == {None}
    assert {r["type_model_id"] for r in rows} == {None}

    # The alert says which model found it — events has no model column, so the
    # description is where that provenance lives.
    alerts = [a for a in await get_latest_alerts(db_session) if a.type == "radio_burst"]
    assert len(alerts) == 1
    assert "BnB v1.0" in alerts[0].message
    assert "Type" not in alerts[0].message


async def test_scan_persists_a_typing_models_burst_type(db_session, monkeypatch):
    start = _recent()
    files = [_fits(s, start) for s in _CORROBORATING]
    _install_scan(monkeypatch, files, lambda name, model_id: _burst_record("Type III"))

    assert await rbs.scan_and_detect_radio_bursts(db_session) == 1
    rows = await detections_for_range(
        db_session, start - timedelta(hours=1), start + timedelta(hours=1)
    )
    assert {r["burst_type"] for r in rows} == {"Type III"}
    assert {r["type_model_id"] for r in rows} == {_MODEL}
    alerts = [a for a in await get_latest_alerts(db_session) if a.type == "radio_burst"]
    assert "Type III" in alerts[0].message


async def test_a_retired_models_recent_rows_are_rescored(db_session, monkeypatch):
    """Dedup is per model, so the scan replaces a retired model's verdicts on the
    recent window instead of leaving them in place."""
    start = _recent()
    files = [_fits(s, start) for s in _CORROBORATING]
    await upsert_detections(db_session, [_stored(s, start, 0.9, "ccm-2.0.1") for s in _CORROBORATING])
    _install_scan(monkeypatch, files, lambda name, model_id: _burst_record())

    await rbs.scan_and_detect_radio_bursts(db_session)

    rows = await detections_for_range(
        db_session, start - timedelta(hours=1), start + timedelta(hours=1)
    )
    # Replaced in place (filename is the PK), not duplicated.
    assert len(rows) == 4
    assert {r["model_id"] for r in rows} == {_MODEL}


async def test_repeat_scan_with_the_same_model_still_dedupes(db_session, monkeypatch):
    start = _recent()
    files = [_fits(s, start) for s in _CORROBORATING]
    calls = [0]

    def _record(name, model_id):
        calls[0] += 1
        return _burst_record()

    _install_scan(monkeypatch, files, _record)

    await rbs.scan_and_detect_radio_bursts(db_session)
    assert calls[0] == 4
    await rbs.scan_and_detect_radio_bursts(db_session)
    assert calls[0] == 4  # nothing re-downloaded or re-scored


async def test_event_rebuild_gates_each_row_by_its_own_model(db_session, monkeypatch):
    """Rows a retired model stored still raise their events, judged by their
    own threshold, until the backfill re-scores them."""
    # Isolate the per-model gate from the high-confidence corroboration rule.
    monkeypatch.setattr(settings, "radio_burst_high_conf_probability", 0.5)
    old = _recent(minutes_ago=5 * 60)
    recent = _recent(minutes_ago=3 * 60)
    await upsert_detections(
        db_session,
        [_stored(s, old, 0.7, "ccm-2.0.1") for s in _CORROBORATING]
        + [_stored(s, recent, 0.7, _MODEL) for s in _CORROBORATING],
    )

    events = await rbs.rebuild_radio_burst_events(db_session)

    # 0.7 clears BnB v1.0's 0.56 but not CCM v2.0.1's 0.80.
    assert [e["start_time"] for e in events] == [recent]


async def test_burst_type_reaches_the_events_api_for_the_timeline(db_session, monkeypatch, client):
    """The Timeline colors the model lane from a structured field, not by parsing
    the description prose, so burst_type has to survive all the way to /api/events."""
    start = _recent()
    files = [_fits(s, start) for s in _CORROBORATING]
    _install_scan(monkeypatch, files, lambda name, model_id: _burst_record("Type II"))
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
    start = _recent()
    files = [_fits(s, start) for s in _CORROBORATING]
    _install_scan(monkeypatch, files, lambda name, model_id: _burst_record(None))
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
    events = rbs.aggregate_events(detections, model_name="CCM v2.0")
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


async def test_models_endpoint_advertises_bnb_v1(client):
    resp = await client.get("/api/radio/models")
    assert resp.status_code == 200
    body = resp.json()

    assert [m["id"] for m in body["models"]] == [_MODEL]
    model = body["models"][0]
    assert model["name"] == "BnB v1.0"
    assert model["kind"] == "binary"
    assert model["threshold"] == pytest.approx(0.5634765625)
    # It does not type bursts, so the UI shows no type controls for it.
    assert model["classes"] == []
    assert model["is_default"] is True
    assert body["default_model"] == _MODEL


async def test_a_retired_model_in_the_configuration_falls_back_to_bnb_v1(client, monkeypatch):
    monkeypatch.setattr(settings, "radio_burst_model", "ccm-2.0.1")
    body = (await client.get("/api/radio/models")).json()
    assert body["default_model"] == _MODEL
    assert body["default_model_source"] == "config"


async def test_predict_rejects_a_retired_or_unknown_model(client):
    for model in ("ccm-9.9.9", "ccm-1.1.0", "ccm-2.0.0", "ccm-2.0.1", "ccmt-1.0.0"):
        resp = await client.post(
            "/api/radio/predict",
            json={"date": _D.isoformat(), "stations": [], "model": model},
        )
        assert resp.status_code == 400
        assert "unknown model" in resp.json()["detail"]


async def test_predict_route_echoes_the_chosen_model(client, monkeypatch):
    async def _list_day_files(day):
        return []

    monkeypatch.setattr(bps, "list_day_files", _list_day_files)
    resp = await client.post(
        "/api/radio/predict",
        json={"date": _D.isoformat(), "stations": [], "model": _MODEL},
    )
    assert resp.status_code == 200
    assert resp.json()["model_id"] == _MODEL


async def test_detections_endpoint_exposes_model_and_type(client, db_session):
    # A row CCM v2.0.1 stored, typed, before the backfill re-scores it.
    start = datetime(2026, 6, 15, 2, 0, tzinfo=timezone.utc)
    await upsert_detections(
        db_session,
        [
            {
                **_stored("BIR", start, 0.97, "ccm-2.0.1"),
                "burst_type": "Type II", "type_confidence": 0.71, "type_model_id": "ccm-2.0.1",
            }
        ],
    )
    body = (await client.get("/api/radio/bursts/detections?date=2026-06-15")).json()
    assert body["count"] == 1
    detection = body["detections"][0]
    assert detection["model_id"] == "ccm-2.0.1"
    assert detection["burst_type"] == "Type II"
    assert detection["type_confidence"] == pytest.approx(0.71)
