"""Tests for the solar-cycle progression feed parsing, service, and route."""
from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient

import app.services.solar_cycle_service as cycle_service
from app.collectors.collect_solar_cycle import parse_observed, parse_predicted
from app.main import app

_OBSERVED = [
    {"time-tag": "2008-11", "ssn": 4.0, "smoothed_ssn": 2.0, "f10.7": 68.0,
     "smoothed_f10.7": 69.0},                       # before `since` -> dropped
    {"time-tag": "2026-06", "ssn": 94.4, "smoothed_ssn": -1.0,
     "observed_swpc_ssn": 104.47, "f10.7": 138.21, "smoothed_f10.7": -1.0},
    {"time-tag": "2019-12", "ssn": 1.5, "smoothed_ssn": 1.8, "f10.7": 69.5,
     "smoothed_f10.7": 70.0},
    "garbage",
    {"time-tag": "bad"},
]

_PREDICTED = [
    {"time-tag": "2026-07", "predicted_ssn": 105.0, "high_ssn": 115.0,
     "low_ssn": 95.0, "predicted_f10.7": 140.0, "high_f10.7": 148.0,
     "low_f10.7": 133.0},
    {"time-tag": "2026-01", "predicted_ssn": 106.3, "high_ssn": 117.3,
     "low_ssn": 98.5, "predicted_f10.7": 141.0, "high_f10.7": 149.3,
     "low_f10.7": 135.1},
]


def test_parse_observed_filters_sorts_and_maps_sentinel():
    rows = parse_observed(_OBSERVED, since="2008-12")
    assert [r["month"] for r in rows] == ["2019-12", "2026-06"]
    assert rows[1]["ssn"] == 94.4
    assert rows[1]["smoothed_ssn"] is None  # -1.0 sentinel -> None
    assert parse_observed("garbage", since="2008-12") == []


def test_parse_predicted_sorts_with_bounds():
    rows = parse_predicted(_PREDICTED)
    assert [r["month"] for r in rows] == ["2026-01", "2026-07"]
    assert rows[0]["ssn_high"] == 117.3 and rows[0]["f107_low"] == 135.1


async def test_service_degrades_per_feed(monkeypatch):
    monkeypatch.setattr(
        cycle_service, "fetch_observed",
        AsyncMock(side_effect=RuntimeError("down")),
    )
    monkeypatch.setattr(
        cycle_service, "fetch_predicted",
        AsyncMock(return_value=parse_predicted(_PREDICTED)),
    )
    resp = await cycle_service.get_solar_cycle()
    assert resp.observed == [] and len(resp.predicted) == 2


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


async def test_solar_cycle_route(client, monkeypatch):
    monkeypatch.setattr(
        cycle_service, "fetch_observed",
        AsyncMock(return_value=parse_observed(_OBSERVED, "2008-12")),
    )
    monkeypatch.setattr(
        cycle_service, "fetch_predicted",
        AsyncMock(return_value=parse_predicted(_PREDICTED)),
    )
    r = await client.get("/api/indices/solar-cycle")
    assert r.status_code == 200
    body = r.json()
    assert body["cycle25_start"] == "2019-12"
    assert body["observed"][0]["month"] == "2019-12"
    assert body["predicted"][0]["ssn"] == 106.3
