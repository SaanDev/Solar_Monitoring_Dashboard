"""Tests for the sunspot-progression and F10.7 radio-flux index routes."""
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient, ASGITransport

from app.collectors.collect_f107 import parse_f107
from app.collectors.collect_sunspot import parse_daily_ssn, parse_monthly_ssn
from app.main import app

_MOCK_INDICES = [
    {"time-tag": "2014-01", "ssn": 112.0, "smoothed_ssn": 102.3, "f10.7": 158.6},
    {"time-tag": "2026-05", "ssn": 101.4, "smoothed_ssn": -1.0, "f10.7": 125.7},
    {"time-tag": "1749-13", "ssn": -1.0, "smoothed_ssn": -1.0, "f10.7": -1.0},  # bad row
]

_MOCK_DAILY_CSV = (
    "2026;06;20;2026.470; 120; 11.0;  30;0\n"
    "2026;06;21;2026.473;  -1;  0.0;   0;0\n"  # missing-day sentinel
    "2026;06;22;2026.476;  98; 10.2;  28;0\n"
)

_MOCK_F107 = [
    {"time_tag": "2026-06-20T20:00:00", "flux": 130},
    {"time_tag": "2026-06-21T20:00:00", "flux": 133},
]


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


def test_parse_monthly_ssn_drops_sentinels_and_smoothes():
    rows = parse_monthly_ssn(_MOCK_INDICES)
    assert len(rows) == 2                       # the -1 ssn row is dropped
    assert rows[0]["smoothed_ssn"] == 102.3
    assert rows[1]["smoothed_ssn"] is None      # -1.0 smoothed becomes None


def test_parse_daily_ssn_skips_missing():
    rows = parse_daily_ssn(_MOCK_DAILY_CSV)
    assert [r["number"] for r in rows] == [120.0, 98.0]


def test_parse_f107():
    rows = parse_f107(_MOCK_F107)
    assert [r["flux"] for r in rows] == [130.0, 133.0]


async def test_sunspot_invalid_scope_rejected(client):
    r = await client.get("/api/indices/sunspot?scope=bogus")
    assert r.status_code == 422


async def test_sunspot_cycle(client):
    with patch(
        "app.services.sunspot_service.fetch_monthly_indices",
        new_callable=AsyncMock,
        return_value=_MOCK_INDICES,
    ):
        r = await client.get("/api/indices/sunspot?scope=cycle")
    assert r.status_code == 200
    body = r.json()
    assert body["scope"] == "cycle"
    assert len(body["data"]) == 2
    assert body["data"][0]["smoothed"] == 102.3


async def test_sunspot_recent(client):
    with patch(
        "app.services.sunspot_service.fetch_daily_ssn_csv",
        new_callable=AsyncMock,
        return_value=_MOCK_DAILY_CSV,
    ):
        r = await client.get("/api/indices/sunspot?scope=recent")
    assert r.status_code == 200
    body = r.json()
    assert body["scope"] == "recent"
    # Recent view filters to ~last year; the mock days are recent, so both survive.
    assert [p["number"] for p in body["data"]] == [120.0, 98.0]


async def test_f107(client):
    with patch(
        "app.services.f107_service.fetch_f107_30day_json",
        new_callable=AsyncMock,
        return_value=_MOCK_F107,
    ):
        r = await client.get("/api/indices/f107")
    assert r.status_code == 200
    body = r.json()
    assert len(body["data"]) == 2
    assert body["data"][1]["flux"] == 133.0
