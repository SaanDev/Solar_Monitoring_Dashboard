"""Tests for the event/alert engine: pure detectors, the detect-and-store pass
(idempotency), range queries, alert derivation, and the API endpoints."""
from datetime import datetime, timedelta, timezone

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.models.timeseries import DstIndex, GoesProton, GoesXrs, KpIndex
from app.processing.event_detection import (
    detect_dst_storms,
    detect_kp_storms,
    detect_proton_events,
    detect_xray_flares,
)
from app.repositories.event_repo import query_range as query_events
from app.repositories.timeseries_repo import upsert_points
from app.services.event_service import detect_and_store, get_events, get_latest_alerts

_T0 = datetime(2026, 6, 1, 0, 0, tzinfo=timezone.utc)
_MIN = timedelta(minutes=1)


def _xrs(base: datetime, fluxes: list[float], step: timedelta = _MIN) -> list[dict]:
    return [
        {"time": base + step * i, "long_channel": f, "short_channel": None, "satellite": 18}
        for i, f in enumerate(fluxes)
    ]


# ── Pure detectors ───────────────────────────────────────────────────────────


def test_flare_detection_span_class_and_bounds():
    flares = detect_xray_flares(_xrs(_T0, [1e-7, 2e-6, 8e-6, 3e-6, 1e-7]))
    assert len(flares) == 1
    f = flares[0]
    assert f["type"] == "xray_flare"
    assert f["severity"] == "C8.0"
    assert f["peak_value"] == 8e-6
    assert f["start_time"] == _T0 + _MIN          # first sample >= C1.0
    assert f["end_time"] == _T0 + 3 * _MIN        # last active before dropping out
    assert f["peak_time"] == _T0 + 2 * _MIN


def test_flare_below_threshold_yields_nothing():
    assert detect_xray_flares(_xrs(_T0, [1e-7, 5e-7, 9e-7])) == []


def test_ongoing_event_has_no_end_time():
    # Still above threshold at the most recent sample -> ongoing.
    flares = detect_xray_flares(_xrs(_T0, [1e-7, 2e-6, 2e-5]))
    assert len(flares) == 1
    assert flares[0]["end_time"] is None
    assert flares[0]["severity"] == "M2.0"


def test_short_gap_merges_long_gap_splits():
    # Two active samples 10 min apart (<= MAX_GAP) -> one event.
    merged = detect_xray_flares(_xrs(_T0, [2e-6], _MIN) + _xrs(_T0 + 10 * _MIN, [2e-6], _MIN))
    assert len(merged) == 1
    # 30 min apart (> MAX_GAP) -> two events.
    split = detect_xray_flares(_xrs(_T0, [2e-6], _MIN) + _xrs(_T0 + 30 * _MIN, [2e-6], _MIN))
    assert len(split) == 2


def test_proton_event_scale():
    pts = [{"time": _T0 + _MIN * i, "flux_gt10": v} for i, v in enumerate([1, 150, 1])]
    events = detect_proton_events(pts)
    assert len(events) == 1
    assert events[0]["type"] == "proton_event"
    assert events[0]["severity"] == "S2"
    assert events[0]["peak_value"] == 150


def test_kp_storm_scale():
    pts = [{"time": _T0 + timedelta(hours=h), "kp": v} for h, v in enumerate([4, 6, 4])]
    events = detect_kp_storms(pts)
    assert len(events) == 1
    assert events[0]["severity"] == "G2"


def test_dst_storm_uses_minimum_as_peak():
    pts = [{"time": _T0 + timedelta(hours=h), "dst": v} for h, v in enumerate([-10, -120, -60, -10])]
    events = detect_dst_storms(pts)
    assert len(events) == 1
    assert events[0]["type"] == "geomagnetic_storm_dst"
    assert events[0]["peak_value"] == -120        # most negative
    assert events[0]["severity"] == "Intense storm"


# ── detect_and_store + repository ────────────────────────────────────────────


def _recent(minutes_ago: int) -> datetime:
    return (datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)).replace(microsecond=0)


async def test_detect_and_store_is_idempotent(db_session):
    base = _recent(120)
    await upsert_points(db_session, GoesXrs, _xrs(base, [1e-7, 2e-6, 8e-6, 3e-6, 1e-7]), "noaa-swpc")

    n1 = await detect_and_store(db_session)
    await detect_and_store(db_session)  # second pass over the same window
    assert n1 >= 1

    rows = await query_events(db_session, base - timedelta(days=1), datetime.now(timezone.utc) + _MIN)
    flares = [r for r in rows if r["type"] == "xray_flare"]
    assert len(flares) == 1  # not duplicated


async def test_alerts_surface_ongoing_event(db_session):
    base = _recent(20)
    # Rising and still elevated at the latest sample -> ongoing M-class flare.
    await upsert_points(db_session, GoesXrs, _xrs(base, [1e-7, 2e-6, 2e-5]), "noaa-swpc")
    await detect_and_store(db_session)

    alerts = await get_latest_alerts(db_session)
    flare_alerts = [a for a in alerts if a.type == "xray_flare"]
    assert len(flare_alerts) == 1
    assert flare_alerts[0].severity == "warning"      # M -> warning
    assert "in progress" in flare_alerts[0].message


async def test_old_subsided_event_not_alerted_but_still_listed(db_session):
    base = _recent(600)  # ~10h ago, beyond the 6h alert linger
    await upsert_points(db_session, GoesXrs, _xrs(base, [1e-7, 2e-6, 8e-6, 3e-6, 1e-7]), "noaa-swpc")
    await detect_and_store(db_session)

    assert [a for a in await get_latest_alerts(db_session) if a.type == "xray_flare"] == []

    events = await get_events(db_session, base - timedelta(days=1), datetime.now(timezone.utc) + _MIN)
    assert any(e.type == "xray_flare" for e in events)


# ── API endpoints ────────────────────────────────────────────────────────────


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


async def test_events_endpoint_empty(client):
    r = await client.get("/api/events")
    assert r.status_code == 200
    assert r.json() == []


async def test_alerts_endpoint_empty(client):
    r = await client.get("/api/alerts/latest")
    assert r.status_code == 200
    assert r.json() == []


async def test_events_endpoint_returns_seeded_event(client, db_session):
    base = _recent(60)
    await upsert_points(db_session, GoesXrs, _xrs(base, [1e-7, 2e-5, 1e-7]), "noaa-swpc")
    await detect_and_store(db_session)

    r = await client.get("/api/events")
    assert r.status_code == 200
    body = r.json()
    flare = next(e for e in body if e["type"] == "xray_flare")
    assert flare["severity"] == "M2.0"
    assert flare["id"].startswith("xray_flare:")


async def test_events_endpoint_rejects_bad_range(client):
    r = await client.get("/api/events?start=2024-01-02&end=2024-01-01")
    assert r.status_code == 400
