"""Tests for the on-demand Burst Predictor: event clustering (ported from
daily_burst_report), result assembly comparing predicted events against a
(mocked) official e-CALLISTO burst list, and the background job lifecycle.

The predictor is deliberately DB-free — scored rows live on the in-memory job
record — so these tests need no database session."""
import asyncio
from datetime import date as date_cls, datetime, timezone

import pytest
from httpx import ASGITransport, AsyncClient

from app.collectors.collect_ecallisto import FitsFile
from app.main import app
from app.schemas.radio_schema import BurstEventsResponse, BurstEventSummary
from app.services import burst_predictor_service as bps

_DAY = "2026-06-15"
_D = date_cls(2026, 6, 15)


def _det(seconds: int, station: str) -> dict:
    return {"seconds": seconds, "station": station}


def test_cluster_events_gap_split():
    # 0s and 300s (5 min) -> one event; 1200s (20 min) later -> a second event.
    dets = [_det(0, "A"), _det(300, "B"), _det(1500, "A")]
    events = bps.cluster_events(dets, gap_minutes=10)
    assert [len(e) for e in events] == [2, 1]


def test_cluster_events_empty():
    assert bps.cluster_events([], 10) == []


def _row(station: str, hh: int, mm: int, prob: float, label: str, alert: str) -> dict:
    start = datetime(2026, 6, 15, hh, mm, 0, tzinfo=timezone.utc)
    return {
        "filename": f"{station}_20260615_{hh:02d}{mm:02d}00_01.fit.gz",
        "station": station,
        "start_time": start,
        "focus": "01",
        "probability": prob,
        "predicted_label": label,
        "alert_level": alert,
    }


async def _empty_official(day):
    return BurstEventsResponse(date=_DAY, count=0, sri_lanka_count=0, events=[])


async def test_assemble_result_filters_and_matches(monkeypatch):
    # A corroborated cluster (4 stations, 2 with p>0.9) plus a lone detection that
    # must be filtered out (not enough stations).
    rows = [
        _row("SRI-Lanka", 2, 0, 0.97, "Burst", "High-confidence burst"),
        _row("HUMAIN", 2, 2, 0.93, "Burst", "High-confidence burst"),
        _row("GLASGOW", 2, 4, 0.70, "Burst", "Likely burst"),
        _row("BIR", 2, 6, 0.65, "Burst", "Likely burst"),
        _row("INDIA-OOTY", 9, 30, 0.96, "Burst", "High-confidence burst"),  # lone -> filtered
        _row("ALASKA", 3, 0, 0.04, "No_Burst", "No alert"),
    ]

    async def _official(day):
        return BurstEventsResponse(
            date=_DAY, count=2, sri_lanka_count=1,
            events=[
                BurstEventSummary(index=0, date=_DAY, start="02:00", end="02:10",
                                  burst_type="III", stations=["SRI-Lanka", "HUMAIN"]),
                BurstEventSummary(index=1, date=_DAY, start="14:00", end="14:05",
                                  burst_type="II", stations=["BIR"]),
            ],
        )

    monkeypatch.setattr(bps, "get_burst_events_for_date", _official)
    result = await bps.assemble_result(rows, _D)

    assert result["total_files"] == 6
    assert result["burst_count"] == 5          # five Burst-labelled (>= 0.595)
    assert result["event_count"] == 1          # only the corroborated 02:00 cluster

    ev = result["events"][0]
    assert ev["start"] == "02:00" and ev["n_stations"] == 4
    assert ev["max_probability"] == pytest.approx(0.97)
    assert ev["matched_official"] is True       # overlaps official 02:00-02:10

    assert result["official_count"] == 2
    assert result["matched_count"] == 1
    off = {o["start"]: o["matched_prediction"] for o in result["official_events"]}
    assert off["02:00"] is True and off["14:00"] is False


async def test_official_events_scoped_to_selected_stations(monkeypatch):
    async def _official(day):
        return BurstEventsResponse(
            date=_DAY, count=2, sri_lanka_count=1,
            events=[
                BurstEventSummary(index=0, date=_DAY, start="02:00", end="02:05",
                                  burst_type="III", stations=["SRI-Lanka", "HUMAIN"]),
                BurstEventSummary(index=1, date=_DAY, start="06:00", end="06:05",
                                  burst_type="II", stations=["GLASGOW", "BIR"]),
            ],
        )

    monkeypatch.setattr(bps, "get_burst_events_for_date", _official)

    # No selection -> all official events.
    res_all = await bps.assemble_result([], _D)
    assert {o["start"] for o in res_all["official_events"]} == {"02:00", "06:00"}

    # Select SRI-Lanka -> only the official event that involves it.
    res_sel = await bps.assemble_result([], _D, ["SRI-Lanka"])
    assert [o["start"] for o in res_sel["official_events"]] == ["02:00"]
    assert res_sel["official_count"] == 1

    # Case-insensitive matching.
    res_ci = await bps.assemble_result([], _D, ["sri-lanka"])
    assert [o["start"] for o in res_ci["official_events"]] == ["02:00"]


async def test_assemble_filters_uncorroborated_events(monkeypatch):
    monkeypatch.setattr(bps, "get_burst_events_for_date", _empty_official)

    # 3 stations -> below the 4-station minimum.
    three = [_row(s, 2, i, 0.95, "Burst", "High-confidence burst") for i, s in enumerate("ABC")]
    assert (await bps.assemble_result(three, _D))["event_count"] == 0

    # 4 stations but only 1 above p>0.9 -> below the high-confidence minimum.
    low_conf = [
        _row("A", 2, 0, 0.95, "Burst", "High-confidence burst"),
        _row("B", 2, 1, 0.70, "Burst", "Likely burst"),
        _row("C", 2, 2, 0.65, "Burst", "Likely burst"),
        _row("D", 2, 3, 0.62, "Burst", "Likely burst"),
    ]
    assert (await bps.assemble_result(low_conf, _D))["event_count"] == 0


async def test_raw_mode_keeps_uncorroborated_events(monkeypatch):
    monkeypatch.setattr(bps, "get_burst_events_for_date", _empty_official)

    # A single-station burst: dropped by the corroboration criteria (needs >= 4
    # stations), but kept in raw mode so the burst is never hidden.
    rows = [_row("INDIA-OOTY", 9, 30, 0.96, "Burst", "High-confidence burst")]

    criteria = await bps.assemble_result(rows, _D)
    assert criteria["raw"] is False
    assert criteria["event_count"] == 0          # corroboration filter drops it

    raw = await bps.assemble_result(rows, _D, raw=True)
    assert raw["raw"] is True
    assert raw["event_count"] == 1               # raw model output keeps it
    assert raw["events"][0]["n_stations"] == 1


async def test_match_uses_full_segment_window(monkeypatch):
    # A corroborated cluster at 09:30 (covers 09:30-09:45); an official burst at
    # 09:40 (inside the segment window) must still match.
    rows = [
        _row("A", 9, 30, 0.95, "Burst", "High-confidence burst"),
        _row("B", 9, 30, 0.93, "Burst", "High-confidence burst"),
        _row("C", 9, 30, 0.70, "Burst", "Likely burst"),
        _row("D", 9, 30, 0.65, "Burst", "Likely burst"),
    ]

    async def _official(day):
        return BurstEventsResponse(
            date=_DAY, count=1, sri_lanka_count=0,
            events=[BurstEventSummary(index=0, date=_DAY, start="09:40", end="09:41",
                                      burst_type="III", stations=["A"])],
        )

    monkeypatch.setattr(bps, "get_burst_events_for_date", _official)
    result = await bps.assemble_result(rows, _D)

    assert result["events"][0]["end"] == "09:45"          # segment end, not start
    assert result["events"][0]["matched_official"] is True
    assert result["matched_count"] == 1


def _fits(station: str, hh: int, mm: int) -> FitsFile:
    start = datetime(2026, 6, 15, hh, mm, 0, tzinfo=timezone.utc)
    name = f"{station}_20260615_{hh:02d}{mm:02d}00_01.fit.gz"
    return FitsFile(station=station, start=start, filename=name, url=f"https://a/{name}", focus="01")


async def test_job_lifecycle_scores_and_assembles(monkeypatch):
    files = [_fits(s, 2, 0) for s in ("A", "B", "C", "D")]  # 4 stations, one window

    async def _list_day_files(day):
        return files

    async def _predict_url(url, filename=None, **kwargs):
        return {"predicted_label": "Burst", "burst_probability": 0.95, "alert_level": "High-confidence burst"}

    monkeypatch.setattr(bps, "list_day_files", _list_day_files)
    monkeypatch.setattr(bps, "predict_url", _predict_url)
    monkeypatch.setattr(bps, "get_burst_events_for_date", _empty_official)

    job_id = bps.start_prediction(_D, [])
    for _ in range(100):  # let the background task finish
        if bps.get_job(job_id)["status"] != "running":
            break
        await asyncio.sleep(0.02)

    job = bps.get_job(job_id)
    assert job["status"] == "done"
    assert job["total"] == 4 and job["scanned"] == 4

    # No DB anywhere in the flow — assemble straight from the job's rows.
    result = await bps.assemble_result(job["rows"], _D)
    assert result["total_files"] == 4
    assert result["burst_count"] == 4
    assert result["event_count"] == 1  # the four cluster into one corroborated event


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


async def test_predict_route_scopes_official_to_selected_stations(client, monkeypatch):
    selection = ["SRI-Lanka", "HUMAIN", "GLASGOW", "BIR"]
    files = [_fits(s, 2, 0) for s in selection]

    async def _list_day_files(day):
        return files

    async def _predict_url(url, filename=None, **kwargs):
        return {"predicted_label": "Burst", "burst_probability": 0.95, "alert_level": "High-confidence burst"}

    async def _official(day):
        return BurstEventsResponse(
            date=_DAY, count=2, sri_lanka_count=1,
            events=[
                BurstEventSummary(index=0, date=_DAY, start="02:00", end="02:05",
                                  burst_type="III", stations=["SRI-Lanka", "HUMAIN"]),
                BurstEventSummary(index=1, date=_DAY, start="06:00", end="06:05",
                                  burst_type="II", stations=["AUSTRIA-UNIGRAZ"]),  # not selected
            ],
        )

    monkeypatch.setattr(bps, "list_day_files", _list_day_files)
    monkeypatch.setattr(bps, "predict_url", _predict_url)
    monkeypatch.setattr(bps, "get_burst_events_for_date", _official)

    start = await client.post("/api/radio/predict", json={"date": _DAY, "stations": selection})
    job_id = start.json()["job_id"]

    body = None
    for _ in range(100):
        r = await client.get(f"/api/radio/predict/{job_id}")
        body = r.json()
        if body["status"] != "running":
            break
        await asyncio.sleep(0.02)

    assert body["status"] == "done"
    official = body["result"]["official_events"]
    # Only the event involving a selected station is shown; the AUSTRIA one is dropped.
    assert [o["start"] for o in official] == ["02:00"]


async def test_predict_status_raw_query_toggles_mode(client, monkeypatch):
    # Two stations (< the 4-station corroboration minimum) -> the cluster is
    # uncorroborated, so criteria mode hides it and raw mode surfaces it. The raw
    # query re-assembles from the cached scores — no re-scoring.
    files = [_fits(s, 2, 0) for s in ("A", "B")]

    async def _list_day_files(day):
        return files

    async def _predict_url(url, filename=None, **kwargs):
        return {"predicted_label": "Burst", "burst_probability": 0.95, "alert_level": "High-confidence burst"}

    monkeypatch.setattr(bps, "list_day_files", _list_day_files)
    monkeypatch.setattr(bps, "predict_url", _predict_url)
    monkeypatch.setattr(bps, "get_burst_events_for_date", _empty_official)

    start = await client.post("/api/radio/predict", json={"date": _DAY, "stations": ["A", "B"]})
    job_id = start.json()["job_id"]

    body = None
    for _ in range(100):
        r = await client.get(f"/api/radio/predict/{job_id}")
        body = r.json()
        if body["status"] != "running":
            break
        await asyncio.sleep(0.02)
    assert body["status"] == "done"

    # Default job mode is criteria -> the uncorroborated cluster is filtered out.
    assert body["result"]["raw"] is False
    assert body["result"]["event_count"] == 0

    # Same job, raw override -> the burst surfaces without re-scoring.
    raw_body = (await client.get(f"/api/radio/predict/{job_id}?raw=true")).json()
    assert raw_body["result"]["raw"] is True
    assert raw_body["result"]["event_count"] == 1


async def _wait_done(job_id: str) -> None:
    for _ in range(200):
        if bps.get_job(job_id)["status"] != "running":
            return
        await asyncio.sleep(0.02)


async def test_predict_processes_all_files_when_uncapped(monkeypatch):
    from app.config import settings

    files = [_fits(f"S{i}", 0, i) for i in range(6)]  # 6 segments for the day

    async def _list_day_files(day):
        return files

    async def _predict_url(url, filename=None, **kwargs):
        return {"predicted_label": "No_Burst", "burst_probability": 0.1, "alert_level": "No alert"}

    monkeypatch.setattr(bps, "list_day_files", _list_day_files)
    monkeypatch.setattr(bps, "predict_url", _predict_url)

    # Default (0 = no limit): every segment is scored.
    monkeypatch.setattr(settings, "radio_burst_predict_max_files", 0)
    job_id = bps.start_prediction(_D, [])
    await _wait_done(job_id)
    assert bps.get_job(job_id)["total"] == 6

    # A positive cap still truncates (safety valve).
    monkeypatch.setattr(settings, "radio_burst_predict_max_files", 3)
    job_id2 = bps.start_prediction(_D, [])
    await _wait_done(job_id2)
    assert bps.get_job(job_id2)["total"] == 3
