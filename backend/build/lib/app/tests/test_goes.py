"""Tests for GOES XRS routes."""
import json
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, patch
import pytest
from httpx import AsyncClient, ASGITransport

from app.main import app

_NOW = datetime.now(timezone.utc)
_START = (_NOW - timedelta(hours=6)).strftime("%Y-%m-%dT%H:%M:%SZ")
_END = _NOW.strftime("%Y-%m-%dT%H:%M:%SZ")

_MOCK_XRS = [
    {"time_tag": _START, "energy": "0.1-0.8nm", "flux": "1.2e-6"},
    {"time_tag": _START, "energy": "0.05-0.4nm", "flux": "3.4e-7"},
]


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


async def test_goes_xrs_invalid_range(client):
    r = await client.get("/api/goes/xrs?start=2024-01-02&end=2024-01-01")
    assert r.status_code == 400


async def test_goes_xrs_range_too_large(client):
    r = await client.get("/api/goes/xrs?start=2024-01-01&end=2024-01-15")
    assert r.status_code == 400


async def test_goes_xrs_returns_structure(client):
    with patch(
        "app.services.goes_xrs_service.fetch_goes_xrs_json",
        new_callable=AsyncMock,
        return_value=_MOCK_XRS,
    ):
        r = await client.get(f"/api/goes/xrs?start={_START}&end={_END}")
    assert r.status_code == 200
    body = r.json()
    assert "data" in body
    assert "start" in body
    assert "end" in body
    assert "satellite" in body


async def test_goes_xrs_latest(client):
    mock = [
        {"time_tag": _START, "energy": "0.05-0.4nm", "flux": "3.4e-7", "satellite": 18},
        {"time_tag": _START, "energy": "0.1-0.8nm", "flux": "5.3e-6", "satellite": 18},
    ]
    with patch(
        "app.services.goes_xrs_service.fetch_goes_xrs_json",
        new_callable=AsyncMock,
        return_value=mock,
    ):
        r = await client.get("/api/goes/xrs/latest")
    assert r.status_code == 200
    body = r.json()
    assert body["satellite"] == 18
    assert body["flare_class"] == "C5.3"  # 5.3e-6 W/m^2 -> C5.3


async def test_goes_proton_latest_and_channel_separation(client):
    # >=100 MeV must NOT leak into the >=10 bucket (substring-collision regression).
    mock = [
        {"time_tag": _START, "energy": ">=10 MeV", "flux": "0.25", "satellite": 18},
        {"time_tag": _START, "energy": ">=50 MeV", "flux": "0.10", "satellite": 18},
        {"time_tag": _START, "energy": ">=100 MeV", "flux": "0.05", "satellite": 18},
    ]
    with patch(
        "app.services.goes_proton_service.fetch_goes_proton_json",
        new_callable=AsyncMock,
        return_value=mock,
    ):
        r = await client.get("/api/goes/proton/latest")
    assert r.status_code == 200
    body = r.json()
    assert body["flux_gt10"] == 0.25
    assert body["flux_gt100"] == 0.05  # not overwritten by the >=10 match
    assert body["storm_scale"] is None  # 0.25 pfu < 10 pfu, no storm
    assert body["event_in_progress"] is False


def test_storm_scale_bands():
    from app.processing.storm_scale import storm_scale

    assert storm_scale(None) is None
    assert storm_scale(5.0) is None       # below 10 pfu
    assert storm_scale(10.0) == "S1"
    assert storm_scale(250.0) == "S2"
    assert storm_scale(5000.0) == "S3"
    assert storm_scale(2.0e4) == "S4"
    assert storm_scale(3.0e5) == "S5"


def test_flare_class_bands():
    from app.processing.flare_class import flare_class

    assert flare_class(None) is None
    assert flare_class(2.0e-8).startswith("A")
    assert flare_class(5.4e-7) == "B5.4"
    assert flare_class(1.2e-6) == "C1.2"
    assert flare_class(3.0e-5) == "M3.0"
    assert flare_class(2.5e-4) == "X2.5"
