"""Tests for the alerts-page activity histograms (per-parameter, time-aligned)."""
from datetime import datetime, time, timedelta, timezone
from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient

import app.services.activity_service as activity_service
import app.services.cme_service as cme_service
from app.main import app
from app.repositories.cme_repo import upsert_cmes
from app.repositories.event_repo import upsert_events
from app.schemas.radio_schema import OfficialBurstItem, OfficialBurstRangeResponse
from app.services.activity_service import get_activity_histogram

UTC = timezone.utc


def _series(resp, key):
    return next(s for s in resp.series if s.key == key)


async def _seed(db, base_date):
    """One event of each parameter across a 2-day window (day0 / day1)."""
    d0 = datetime.combine(base_date, time(12, 0), tzinfo=UTC)
    d1 = d0 + timedelta(days=1)
    await upsert_events(
        db,
        [
            {"type": "xray_flare", "start_time": d0, "severity": "M5.0", "description": ""},
            {"type": "xray_flare", "start_time": d0 + timedelta(hours=1),
             "severity": "C2.0", "description": ""},
            {"type": "radio_burst", "start_time": d0, "severity": "Likely burst",
             "description": ""},
            {"type": "geomagnetic_storm_kp", "start_time": d1, "severity": "G2",
             "description": ""},
            {"type": "geomagnetic_storm_dst", "start_time": d1,
             "severity": "Intense storm", "description": ""},
        ],
    )
    await upsert_cmes(
        db,
        [{"activity_id": "cme-a", "start_time": d0, "is_earth_directed": True,
          "predicted_arrival_time": d0 + timedelta(days=2), "speed": 800.0,
          "note": ""}],
    )


def _official(base_date):
    d0 = datetime.combine(base_date, time(12, 0), tzinfo=UTC)
    return OfficialBurstRangeResponse(
        start=base_date.isoformat(),
        end=base_date.isoformat(),
        events=[
            OfficialBurstItem(start_time=d0, end_time=d0 + timedelta(minutes=5),
                              burst_type="III", stations=["ALASKA"]),
            OfficialBurstItem(start_time=d0, end_time=d0 + timedelta(minutes=8),
                              burst_type="II", stations=["BIR"]),
        ],
    )


async def test_activity_histogram_buckets_each_parameter(db_session, monkeypatch):
    base = (datetime.now(UTC) - timedelta(days=3)).date()
    # Avoid the on-demand DONKI fetch hitting the network.
    monkeypatch.setattr(cme_service, "fetch_cmes", AsyncMock(return_value=[]))
    monkeypatch.setattr(
        activity_service, "get_official_bursts_range",
        AsyncMock(return_value=_official(base)),
    )
    await _seed(db_session, base)

    resp = await get_activity_histogram(db_session, base, base + timedelta(days=1), 1)

    assert resp.interval_days == 1
    assert len(resp.bin_starts) == 2
    assert [s.key for s in resp.series] == [
        "flares", "radio_official", "radio_model", "cme", "geomagnetic"
    ]

    flares = _series(resp, "flares")
    assert flares.categories == ["C", "M"]          # ordered low→high, trimmed
    assert flares.counts == [[1, 1], [0, 0]]        # both on day0
    assert flares.total == 2

    official = _series(resp, "radio_official")
    assert official.categories == ["Type II", "Type III"]
    assert official.counts[0] == [1, 1]

    model = _series(resp, "radio_model")
    assert model.categories == ["Likely burst"]

    cme = _series(resp, "cme")
    assert cme.categories == ["Not Earth-directed", "Earth-directed"]
    assert cme.counts[0] == [0, 1]                  # the one CME is Earth-directed

    geo = _series(resp, "geomagnetic")
    # Kp "G2" + Dst "Intense storm"→"G4", both on day1.
    assert geo.categories == ["G2", "G4"]
    assert geo.counts[1] == [1, 1]


async def test_activity_histogram_wider_bin_merges_days(db_session, monkeypatch):
    base = (datetime.now(UTC) - timedelta(days=3)).date()
    monkeypatch.setattr(cme_service, "fetch_cmes", AsyncMock(return_value=[]))
    monkeypatch.setattr(
        activity_service, "get_official_bursts_range",
        AsyncMock(return_value=_official(base)),
    )
    await _seed(db_session, base)

    resp = await get_activity_histogram(db_session, base, base + timedelta(days=1), 3)
    assert len(resp.bin_starts) == 1                # one 3-day bin covers both days
    geo = _series(resp, "geomagnetic")
    assert geo.counts == [[1, 1]]


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


async def test_activity_histogram_route(client, db_session, monkeypatch):
    base = (datetime.now(UTC) - timedelta(days=3)).date()
    monkeypatch.setattr(cme_service, "fetch_cmes", AsyncMock(return_value=[]))
    monkeypatch.setattr(
        activity_service, "get_official_bursts_range",
        AsyncMock(return_value=OfficialBurstRangeResponse(
            start=base.isoformat(), end=base.isoformat(), events=[])),
    )
    await _seed(db_session, base)

    r = await client.get(
        f"/api/events/activity-histogram?start={base}&end={base + timedelta(days=1)}&interval=1"
    )
    assert r.status_code == 200
    body = r.json()
    assert {s["key"] for s in body["series"]} == {
        "flares", "radio_official", "radio_model", "cme", "geomagnetic"
    }
    # unordered window / bad interval rejected
    assert (
        await client.get(
            f"/api/events/activity-histogram?start={base + timedelta(days=5)}&end={base}&interval=1"
        )
    ).status_code == 422
    assert (
        await client.get(
            f"/api/events/activity-histogram?start={base}&end={base}&interval=0"
        )
    ).status_code == 422
