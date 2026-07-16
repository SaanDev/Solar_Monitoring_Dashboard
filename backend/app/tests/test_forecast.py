"""Tests for the forecasting layer: Newell coupling / predicted-Kp math,
DONKI CME parsing + event mapping, NOAA scales / hemispheric-power parsing,
predicted-storm detection, and the /api/forecast routes."""
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient

import app.api.routes_forecast as routes_forecast
import app.services.cme_service as cme_service
import app.services.forecast_service as forecast_service
from app.collectors.collect_donki import parse_cmes, pick_analysis, pick_enlil
from app.collectors.collect_noaa_forecast import parse_hemi_power, parse_noaa_scales
from app.main import app
from app.processing.kp_prediction import (
    newell_coupling,
    predict_series,
    predicted_kp,
    predicted_storm_events,
    smooth_series,
)
from app.repositories.cme_repo import upsert_cmes
from app.schemas.forecast_schema import (
    KpForecastLatest,
    KpForecastResponse,
    NoaaScalesResponse,
)

UTC = timezone.utc


@pytest.fixture(autouse=True)
def stub_ambient_wind(monkeypatch):
    """Keep CME enrichment hermetic: the DBM ambient wind is read from the live
    NOAA solar-wind feed, so pin it to a fixed value instead of hitting the net."""
    monkeypatch.setattr(cme_service, "recent_ambient_speed", AsyncMock(return_value=420.0))


# ── Newell coupling / predicted Kp ───────────────────────────────────────────


def test_coupling_zero_for_northward_imf():
    # Purely northward IMF opens no flux at the magnetopause.
    assert newell_coupling(500.0, 0.0, 8.0) == pytest.approx(0.0, abs=1e-9)


def test_coupling_maximal_for_southward_imf():
    south = newell_coupling(500.0, 0.0, -8.0)
    oblique = newell_coupling(500.0, 8.0, 0.0)
    assert south > oblique > 0


def test_coupling_grows_with_speed_and_missing_inputs_are_none():
    assert newell_coupling(800.0, 0.0, -8.0) > newell_coupling(400.0, 0.0, -8.0)
    assert newell_coupling(None, 0.0, -8.0) is None
    assert newell_coupling(400.0, None, -8.0) is None


def test_predicted_kp_realistic_and_clamped():
    # Quiet wind: ~400 km/s, weak northward field -> low Kp.
    quiet = predicted_kp(newell_coupling(380.0, 1.0, 3.0), 4.0, 380.0)
    assert quiet < 3
    # Severe driving: fast wind, strong southward field -> storm-level Kp,
    # never above the index ceiling.
    storm = predicted_kp(newell_coupling(750.0, 10.0, -25.0), 20.0, 750.0)
    assert 5 <= storm <= 9
    assert predicted_kp(None, 5.0, 400.0) is None
    assert predicted_kp(1e9, 5.0, 400.0) == 9.0


def test_smooth_series_trailing_mean_skips_gaps():
    t0 = datetime(2026, 7, 4, 0, 0, tzinfo=UTC)
    pts = [
        {"time": t0, "kp": 2.0, "coupling": 100.0},
        {"time": t0 + timedelta(minutes=30), "kp": None, "coupling": None},  # gap
        {"time": t0 + timedelta(minutes=60), "kp": 4.0, "coupling": 300.0},
        # 2 h later: the first two points have left the trailing window.
        {"time": t0 + timedelta(minutes=180), "kp": 6.0, "coupling": 500.0},
    ]
    sm = smooth_series(pts)
    assert sm[1]["kp"] == 2.0                       # gap contributes nothing
    assert sm[2]["kp"] == pytest.approx(3.0)        # mean of 2 and 4
    assert sm[3]["kp"] == 6.0                       # window slid past old points


def test_predicted_storm_events_segments_episodes():
    t0 = datetime(2026, 7, 4, 0, 0, tzinfo=UTC)
    samples = [(t0 + timedelta(minutes=i), 3.0) for i in range(0, 60, 5)]
    samples += [(t0 + timedelta(minutes=60 + i), 6.2) for i in range(0, 60, 5)]
    samples += [(t0 + timedelta(minutes=120 + i), 3.0) for i in range(0, 60, 5)]
    events = predicted_storm_events(samples)
    assert len(events) == 1
    e = events[0]
    assert e["type"] == "geomagnetic_storm_prediction"
    assert e["severity"] == "G2"
    assert e["start_time"] == t0 + timedelta(minutes=60)
    assert e["end_time"] is not None  # quiet samples follow, so not ongoing
    assert predicted_storm_events([(t0, 2.0), (t0 + timedelta(minutes=5), None)]) == []


def test_predict_series_keeps_gaps():
    t0 = datetime(2026, 7, 4, 0, 0, tzinfo=UTC)
    out = predict_series(
        [
            {"time": t0, "speed": 500.0, "density": 5.0, "by": 3.0, "bz": -6.0},
            {"time": t0 + timedelta(minutes=1), "speed": None, "density": None,
             "by": None, "bz": None},
        ]
    )
    assert out[0]["kp"] is not None and out[0]["coupling"] > 0
    assert out[1]["kp"] is None


# ── DONKI CME parsing ────────────────────────────────────────────────────────

_DONKI_CME = {
    "activityID": "2026-07-01T12:36:00-CME-001",
    "startTime": "2026-07-01T12:36Z",
    "sourceLocation": "N15W20",
    "activeRegionNum": 14135,
    "note": "Halo CME associated with the X1.2 flare.",
    "link": "https://kauai.ccmc.gsfc.nasa.gov/DONKI/view/CME/12345/-1",
    "cmeAnalyses": [
        {  # superseded early fit
            "isMostAccurate": False,
            "time21_5": "2026-07-01T17:00Z",
            "latitude": 10.0, "longitude": 15.0, "halfAngle": 30.0,
            "speed": 900.0, "type": "C",
            "submissionTime": "2026-07-01T14:00Z",
            "enlilList": [],
        },
        {
            "isMostAccurate": True,
            "time21_5": "2026-07-01T16:24Z",
            "latitude": 12.0, "longitude": 18.0, "halfAngle": 42.0,
            "speed": 1100.0, "type": "O",
            "submissionTime": "2026-07-01T20:00Z",
            "enlilList": [
                {  # older run without an Earth arrival
                    "modelCompletionTime": "2026-07-01T18:00Z",
                    "estimatedShockArrivalTime": None,
                    "kp_90": None, "kp_135": None, "kp_180": None,
                },
                {
                    "modelCompletionTime": "2026-07-01T21:00Z",
                    "estimatedShockArrivalTime": "2026-07-03T06:00Z",
                    "kp_90": 5.0, "kp_135": 6.0, "kp_180": 7.0,
                },
            ],
        },
    ],
}


def test_parse_cmes_picks_operative_analysis_and_enlil_run():
    records = parse_cmes([_DONKI_CME, {"no": "id"}, "garbage"])
    assert len(records) == 1
    r = records[0]
    assert r["activity_id"] == "2026-07-01T12:36:00-CME-001"
    assert r["start_time"] == datetime(2026, 7, 1, 12, 36, tzinfo=UTC)
    assert r["speed"] == 1100.0 and r["half_angle"] == 42.0  # isMostAccurate fit
    assert r["is_earth_directed"] is True
    assert r["predicted_arrival_time"] == datetime(2026, 7, 3, 6, 0, tzinfo=UTC)
    assert r["predicted_kp"] == 7.0  # max of the run's kp_* angles
    assert r["active_region"] == 14135


def test_parse_cmes_without_analysis_degrades():
    bare = {"activityID": "x-CME-002", "startTime": "2026-07-02T00:00Z"}
    r = parse_cmes([bare])[0]
    assert r["speed"] is None and r["is_earth_directed"] is False
    assert r["predicted_arrival_time"] is None


def test_pick_helpers_prefer_latest():
    assert pick_analysis(None) == {}
    latest = {"submissionTime": "2026-07-02T00:00Z"}
    assert pick_analysis([{"submissionTime": "2026-07-01T00:00Z"}, latest]) is latest
    assert pick_enlil(None) == {}
    with_arrival = {"estimatedShockArrivalTime": "2026-07-03T00:00Z",
                    "modelCompletionTime": "2026-07-01T00:00Z"}
    assert pick_enlil([{"modelCompletionTime": "2026-07-02T00:00Z"}, with_arrival]) is with_arrival


def test_cme_to_event_spans_launch_to_arrival():
    r = parse_cmes([_DONKI_CME])[0]
    e = cme_service.cme_to_event(r)
    assert e["type"] == "cme"
    assert e["start_time"] == r["start_time"]
    assert e["end_time"] == r["predicted_arrival_time"]  # ENLIL arrival preferred
    assert e["severity"] == "G3"  # predicted Kp 7
    assert "predicted arrival 2026-07-03 06:00 UTC (WSA-ENLIL)" in e["description"]


# A geoeffective CME DONKI never ran ENLIL on: measured cone speed + direction,
# but no ``estimatedShockArrivalTime`` -> no ENLIL arrival.
_DONKI_CME_NO_ENLIL = {
    "activityID": "2026-07-02T00:00:00-CME-009",
    "startTime": "2026-07-02T00:00Z",
    "sourceLocation": "S05W08",
    "activeRegionNum": 14140,
    "note": "",
    "link": "https://kauai.ccmc.gsfc.nasa.gov/DONKI/view/CME/9/-1",
    "cmeAnalyses": [
        {
            "isMostAccurate": True,
            "time21_5": "2026-07-02T04:00Z",
            "latitude": 5.0, "longitude": 8.0, "halfAngle": 40.0,
            "speed": 850.0, "type": "C",
            "submissionTime": "2026-07-02T06:00Z",
            "enlilList": [],  # never modelled -> no ENLIL arrival
        }
    ],
}


def test_cme_to_event_uses_dbm_arrival_when_no_enlil():
    r = cme_service.enrich_cme(parse_cmes([_DONKI_CME_NO_ENLIL])[0], w=420.0)
    e = cme_service.cme_to_event(r)
    assert e["type"] == "cme"
    assert e["end_time"] == r["predicted_arrival_dbm"]  # DBM fills in for ENLIL
    assert e["end_time"] is not None
    assert "(DBM)" in e["description"]


# ── NOAA scales + hemispheric power parsing ──────────────────────────────────

_SCALES = {
    "0": {"DateStamp": "2026-07-04", "TimeStamp": "07:41:00",
          "R": {"Scale": "0", "Text": "none", "MinorProb": None, "MajorProb": None},
          "S": {"Scale": "0", "Text": "none", "Prob": None},
          "G": {"Scale": "0", "Text": "none"}},
    "1": {"DateStamp": "2026-07-04", "TimeStamp": "07:41:00",
          "R": {"Scale": None, "Text": None, "MinorProb": "70", "MajorProb": "20"},
          "S": {"Scale": None, "Text": None, "Prob": "20"},
          "G": {"Scale": "3", "Text": "strong"}},
    "2": {"DateStamp": "2026-07-05", "TimeStamp": "00:00:00",
          "R": {"Scale": None, "Text": None, "MinorProb": "70", "MajorProb": "20"},
          "S": {"Scale": None, "Text": None, "Prob": "20"},
          "G": {"Scale": "1", "Text": "minor"}},
    "3": {"DateStamp": "2026-07-06", "TimeStamp": "00:00:00",
          "R": {"Scale": None, "Text": None, "MinorProb": "55", "MajorProb": "10"},
          "S": {"Scale": None, "Text": None, "Prob": "10"},
          "G": {"Scale": "0", "Text": "none"}},
    "-1": {"DateStamp": "2026-07-03", "TimeStamp": "07:41:00",
           "R": {"Scale": "2", "Text": "moderate", "MinorProb": None, "MajorProb": None},
           "S": {"Scale": "0", "Text": "none", "Prob": None},
           "G": {"Scale": "3", "Text": "strong"}},
}


def test_parse_noaa_scales():
    p = parse_noaa_scales(_SCALES)
    assert p["issued"] == datetime(2026, 7, 4, 7, 41, tzinfo=UTC)
    assert p["observed"]["r_scale"] == "2"
    assert p["current"]["g_scale"] == "0"
    assert [d["g_scale"] for d in p["forecast"]] == ["3", "1", "0"]
    assert p["forecast"][0]["r_minor_prob"] == 70  # "70" -> int
    assert parse_noaa_scales("garbage")["forecast"] == []


def test_parse_hemi_power_takes_last_row():
    text = (
        "# comment\n"
        "2026-07-04_00:00    2026-07-04_00:44      23      27\n"
        "2026-07-04_00:05    2026-07-04_00:49      24      28\n"
        "bad line\n"
    )
    p = parse_hemi_power(text)
    assert p["north_gw"] == 24.0 and p["south_gw"] == 28.0
    assert p["observation_time"] == datetime(2026, 7, 4, 0, 5, tzinfo=UTC)
    assert parse_hemi_power("# only comments\n") is None


# ── Services ─────────────────────────────────────────────────────────────────


async def test_predicted_storm_detection_stores_events(db_session, monkeypatch):
    now = datetime.now(UTC).replace(second=0, microsecond=0)
    # 2 h of strongly-driven wind ending now -> one ongoing predicted storm.
    points = [
        {"time": now - timedelta(minutes=m), "speed": 800.0, "density": 10.0,
         "by": 0.0, "bz": -20.0}
        for m in range(120, -1, -1)
    ]
    monkeypatch.setattr(
        forecast_service, "fetch_coupling_series", AsyncMock(return_value=points)
    )
    count = await forecast_service.detect_and_store_predicted_storms(db_session)
    assert count == 1

    from app.repositories.event_repo import query_all

    rows = await query_all(db_session)
    assert rows[0]["type"] == "geomagnetic_storm_prediction"
    assert rows[0]["severity"].startswith("G")
    assert rows[0]["end_time"] is None  # still driven at the last sample


async def test_predicted_storm_detection_survives_feed_outage(db_session, monkeypatch):
    monkeypatch.setattr(
        forecast_service,
        "fetch_coupling_series",
        AsyncMock(side_effect=RuntimeError("feed down")),
    )
    assert await forecast_service.detect_and_store_predicted_storms(db_session) == 0


async def test_cme_collect_reconciles_events(db_session, monkeypatch):
    r = parse_cmes([_DONKI_CME])[0]
    monkeypatch.setattr(cme_service, "fetch_cmes", AsyncMock(return_value=[r]))
    assert await cme_service.collect_and_store(db_session) == 1

    from app.repositories.event_repo import query_all

    rows = await query_all(db_session)
    assert [e["type"] for e in rows] == ["cme"]

    # A revised analysis withdraws the Earth arrival AND re-points the cone to the
    # limb (no longer geoeffective) -> the event is reconciled away.
    revised = {
        **r,
        "is_earth_directed": False,
        "predicted_arrival_time": None,
        "latitude": 0.0,
        "longitude": 120.0,
        "half_angle": 20.0,
    }
    monkeypatch.setattr(cme_service, "fetch_cmes", AsyncMock(return_value=[revised]))
    await cme_service.collect_and_store(db_session)
    assert await query_all(db_session) == []


async def test_cme_collect_includes_geoeffective_without_enlil(db_session, monkeypatch):
    # A CME DONKI never modelled still reaches the event feed via the cone-geometry
    # geoeffective check, its span closed by the DBM arrival.
    r = parse_cmes([_DONKI_CME_NO_ENLIL])[0]
    monkeypatch.setattr(cme_service, "fetch_cmes", AsyncMock(return_value=[r]))
    await cme_service.collect_and_store(db_session)

    from app.repositories.event_repo import query_all

    rows = await query_all(db_session)
    assert [e["type"] for e in rows] == ["cme"]
    assert rows[0]["end_time"] is not None
    assert "(DBM)" in rows[0]["description"]


# ── Routes ───────────────────────────────────────────────────────────────────


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


async def test_kp_route(client, monkeypatch):
    t = datetime(2026, 7, 4, 10, 0, tzinfo=UTC)
    monkeypatch.setattr(
        routes_forecast,
        "get_kp_forecast",
        AsyncMock(
            return_value=KpForecastResponse(
                range="1-day",
                latest=KpForecastLatest(time=t, kp=5.6, coupling=25000.0, g_scale="G1"),
                data=[{"time": t, "kp": 5.6}],
            )
        ),
    )
    r = await client.get("/api/forecast/kp?range=1-day")
    assert r.status_code == 200
    assert r.json()["latest"]["g_scale"] == "G1"

    assert (await client.get("/api/forecast/kp?range=30-day")).status_code == 422


async def test_cmes_route_reads_catalog(client, db_session):
    await upsert_cmes(db_session, parse_cmes([_DONKI_CME]))
    r = await client.get("/api/forecast/cmes?days=30")
    assert r.status_code == 200
    body = r.json()
    assert body["cmes"][0]["activity_id"] == "2026-07-01T12:36:00-CME-001"
    assert body["cmes"][0]["is_earth_directed"] is True

    assert (await client.get("/api/forecast/cmes?days=99")).status_code == 422


async def test_cmes_route_enriches_with_dbm_forecast(client, db_session):
    # A CME with a cone speed but no ENLIL run still gets an SWDash DBM arrival.
    await upsert_cmes(db_session, parse_cmes([_DONKI_CME_NO_ENLIL]))
    r = await client.get("/api/forecast/cmes?days=30")
    assert r.status_code == 200
    c = r.json()["cmes"][0]
    assert c["is_earth_directed"] is False        # DONKI never modelled it
    assert c["geoeffective"] is True              # but its cone contains Earth
    assert c["arrival_model"] == "DBM"
    assert c["predicted_arrival_dbm"] is not None
    assert c["arrival_earliest"] is not None and c["arrival_latest"] is not None
    assert c["impact_speed_km_s"] is not None
    assert c["transit_hours"] is not None
    assert c["ambient_wind_km_s"] == pytest.approx(420.0)


async def test_cmes_history_reads_catalog_within_window(client, db_session, monkeypatch):
    # A window inside the retained rolling catalog serves from the DB and must
    # NOT trigger an on-demand DONKI fetch.
    fetch = AsyncMock(return_value=[])
    monkeypatch.setattr(cme_service, "fetch_cmes", fetch)
    await upsert_cmes(db_session, parse_cmes([_DONKI_CME]))

    r = await client.get("/api/forecast/cmes/history?start=2026-07-01&end=2026-07-02")
    assert r.status_code == 200
    body = r.json()
    assert body["cmes"][0]["activity_id"] == "2026-07-01T12:36:00-CME-001"
    fetch.assert_not_awaited()


async def test_cmes_history_fetches_old_window_on_demand(client, db_session, monkeypatch):
    # A window older than the retained catalog is fetched on demand + upserted.
    fetch = AsyncMock(return_value=parse_cmes([_DONKI_CME]))
    monkeypatch.setattr(cme_service, "fetch_cmes", fetch)

    r = await client.get("/api/forecast/cmes/history?start=2020-01-01&end=2020-01-31")
    assert r.status_code == 200
    fetch.assert_awaited_once()


async def test_cmes_history_validates_range(client):
    # end before start, and an over-long span, are rejected.
    assert (
        await client.get("/api/forecast/cmes/history?start=2026-07-05&end=2026-07-01")
    ).status_code == 422
    assert (
        await client.get("/api/forecast/cmes/history?start=2020-01-01&end=2026-01-01")
    ).status_code == 422


async def test_cme_histogram_buckets_by_interval(db_session, monkeypatch):
    # Two CMEs a day apart -> one per daily bin, both in the same 3-day bin.
    day1 = {**parse_cmes([_DONKI_CME])[0], "activity_id": "a"}
    day2 = {
        **day1,
        "activity_id": "b",
        "start_time": day1["start_time"] + timedelta(days=1),
        "is_earth_directed": False,
        "predicted_arrival_time": None,
    }
    await upsert_cmes(db_session, [day1, day2])

    start = day1["start_time"].date()
    end = start + timedelta(days=2)

    daily = await cme_service.get_cme_histogram(db_session, start, end, 1)
    assert daily.interval_days == 1
    assert [b.count for b in daily.bins] == [1, 1, 0]
    assert [b.earth_directed for b in daily.bins] == [1, 0, 0]

    every3 = await cme_service.get_cme_histogram(db_session, start, end, 3)
    assert [b.count for b in every3.bins] == [2]  # one bin spanning the window
    assert every3.bins[0].earth_directed == 1


async def test_cmes_histogram_route(client, db_session):
    await upsert_cmes(db_session, parse_cmes([_DONKI_CME]))
    r = await client.get(
        "/api/forecast/cmes/histogram?start=2026-07-01&end=2026-07-03&interval=1"
    )
    assert r.status_code == 200
    body = r.json()
    assert body["interval_days"] == 1
    assert sum(b["count"] for b in body["bins"]) == 1
    # interval outside 1..30 and an unordered window are rejected.
    assert (
        await client.get(
            "/api/forecast/cmes/histogram?start=2026-07-01&end=2026-07-03&interval=0"
        )
    ).status_code == 422
    assert (
        await client.get(
            "/api/forecast/cmes/histogram?start=2026-07-05&end=2026-07-01&interval=1"
        )
    ).status_code == 422


async def test_noaa_scales_route(client, monkeypatch):
    monkeypatch.setattr(
        routes_forecast,
        "get_noaa_scales",
        AsyncMock(return_value=NoaaScalesResponse.model_validate(parse_noaa_scales(_SCALES))),
    )
    r = await client.get("/api/forecast/noaa-scales")
    assert r.status_code == 200
    assert r.json()["forecast"][0]["g_scale"] == "3"


async def test_aurora_route(client, monkeypatch):
    monkeypatch.setattr(
        forecast_service, "fetch_hemi_power",
        AsyncMock(return_value={"observation_time": datetime(2026, 7, 4, 0, 5, tzinfo=UTC),
                                "forecast_time": None, "north_gw": 24.0, "south_gw": 28.0}),
    )
    r = await client.get("/api/forecast/aurora")
    assert r.status_code == 200
    body = r.json()
    assert body["power_north_gw"] == 24.0
    assert body["north_image_url"].endswith("/images/animations/ovation/north/latest.jpg")
