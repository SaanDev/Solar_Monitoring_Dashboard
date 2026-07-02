"""Tests for the GOES electron-flux and magnetometer routes + collectors."""
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient, ASGITransport

from app.collectors.collect_goes_electrons import records_from_raw as electron_records
from app.collectors.collect_goes_magnetometer import records_from_raw as mag_records
from app.main import app

_NOW = datetime.now(timezone.utc)
_START = (_NOW - timedelta(hours=6)).strftime("%Y-%m-%dT%H:%M:%SZ")
_END = _NOW.strftime("%Y-%m-%dT%H:%M:%SZ")

_MOCK_ELECTRONS = [
    {"time_tag": _START, "satellite": 19, "flux": 167.6, "energy": ">=2 MeV"},
    # An unrelated energy band must be ignored, not crash the parser.
    {"time_tag": _START, "satellite": 19, "flux": 999.0, "energy": ">=0.8 MeV"},
]

_MOCK_MAG = [
    {"time_tag": _START, "satellite": 18, "He": 17.7, "Hp": 91.9, "Hn": 11.6, "total": 94.3},
]


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


def test_electron_parser_keeps_only_ge2mev():
    rows = electron_records(_MOCK_ELECTRONS)
    assert len(rows) == 1
    assert rows[0]["flux_ge2mev"] == 167.6
    assert rows[0]["satellite"] == 19


def test_magnetometer_parser_maps_components():
    rows = mag_records(_MOCK_MAG)
    assert rows[0]["hp"] == 91.9
    assert rows[0]["he"] == 17.7
    assert rows[0]["hn"] == 11.6
    assert rows[0]["total"] == 94.3


async def test_electrons_invalid_range(client):
    r = await client.get("/api/goes/electrons?start=2024-01-02&end=2024-01-01")
    assert r.status_code == 400


async def test_electrons_returns_structure(client):
    with patch(
        "app.services.goes_electron_service.fetch_goes_electrons_json",
        new_callable=AsyncMock,
        return_value=_MOCK_ELECTRONS,
    ):
        r = await client.get(f"/api/goes/electrons?start={_START}&end={_END}")
    assert r.status_code == 200
    body = r.json()
    assert {"data", "start", "end", "satellite"} <= body.keys()


async def test_electrons_latest(client):
    with patch(
        "app.services.goes_electron_service.fetch_goes_electrons_json",
        new_callable=AsyncMock,
        return_value=_MOCK_ELECTRONS,
    ):
        r = await client.get("/api/goes/electrons/latest")
    assert r.status_code == 200
    body = r.json()
    assert body["satellite"] == 19
    assert body["flux_ge2mev"] == 167.6


async def test_magnetometer_returns_structure(client):
    with patch(
        "app.services.goes_magnetometer_service.fetch_goes_magnetometer_json",
        new_callable=AsyncMock,
        return_value=_MOCK_MAG,
    ):
        r = await client.get(f"/api/goes/magnetometer?start={_START}&end={_END}")
    assert r.status_code == 200
    body = r.json()
    assert {"data", "start", "end", "satellite"} <= body.keys()


async def test_magnetometer_latest(client):
    with patch(
        "app.services.goes_magnetometer_service.fetch_goes_magnetometer_json",
        new_callable=AsyncMock,
        return_value=_MOCK_MAG,
    ):
        r = await client.get("/api/goes/magnetometer/latest")
    assert r.status_code == 200
    body = r.json()
    assert body["satellite"] == 18
    assert body["total"] == 94.3
    assert body["hp"] == 91.9
