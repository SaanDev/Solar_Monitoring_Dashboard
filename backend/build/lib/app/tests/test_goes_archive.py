"""Tests for GOES XRS/proton archive downloads (raw CSV/JSON + rendered PNG)."""
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

import app.api.routes_goes as rg
from app.main import app
from app.schemas.goes_schema import (
    GoesProtonPoint,
    GoesProtonResponse,
    GoesXrsPoint,
    GoesXrsResponse,
)

_T0 = datetime(2025, 1, 15, 0, 0, tzinfo=timezone.utc)
_START = "2025-01-15T00:00:00Z"
_END = "2025-01-15T01:00:00Z"

_XRS = GoesXrsResponse(
    start=_T0, end=_T0 + timedelta(hours=1), satellite=18,
    data=[
        GoesXrsPoint(time=_T0, short_channel=3.0e-7, long_channel=1.0e-6),
        GoesXrsPoint(time=_T0 + timedelta(minutes=1), short_channel=None, long_channel=2.0e-6),
    ],
)
_PROTON = GoesProtonResponse(
    start=_T0, end=_T0 + timedelta(hours=1), satellite=18,
    data=[GoesProtonPoint(time=_T0, flux_gt10=0.5, flux_gt50=0.1, flux_gt100=0.05)],
)


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


async def test_xrs_download_csv(client):
    with patch.object(rg, "get_goes_xrs", new=AsyncMock(return_value=_XRS)):
        r = await client.get(f"/api/goes/xrs/download?start={_START}&end={_END}&format=csv")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")
    assert "attachment" in r.headers["content-disposition"]
    assert ".csv" in r.headers["content-disposition"]
    assert "time,short_channel_wm2,long_channel_wm2" in r.text
    assert "1e-06" in r.text  # long channel of first point


async def test_xrs_download_json(client):
    with patch.object(rg, "get_goes_xrs", new=AsyncMock(return_value=_XRS)):
        r = await client.get(f"/api/goes/xrs/download?start={_START}&end={_END}&format=json")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/json")
    assert "attachment" in r.headers["content-disposition"]
    assert "data" in r.json()


async def test_xrs_plot_png_inline_and_download(client):
    with patch.object(rg, "get_goes_xrs", new=AsyncMock(return_value=_XRS)):
        inline = await client.get(f"/api/goes/xrs/plot?start={_START}&end={_END}")
        dl = await client.get(f"/api/goes/xrs/plot?start={_START}&end={_END}&download=1")
    assert inline.status_code == 200
    assert inline.headers["content-type"] == "image/png"
    assert inline.content[:8] == b"\x89PNG\r\n\x1a\n"  # valid PNG signature
    assert "attachment" not in inline.headers.get("content-disposition", "")
    assert "attachment" in dl.headers["content-disposition"]


async def test_proton_download_csv_and_plot(client):
    with patch.object(rg, "get_goes_proton", new=AsyncMock(return_value=_PROTON)):
        csv_r = await client.get(f"/api/goes/proton/download?start={_START}&end={_END}&format=csv")
        png_r = await client.get(f"/api/goes/proton/plot?start={_START}&end={_END}")
    assert csv_r.status_code == 200
    assert "flux_gt10_pfu,flux_gt50_pfu,flux_gt100_pfu" in csv_r.text
    assert png_r.status_code == 200
    assert png_r.content[:8] == b"\x89PNG\r\n\x1a\n"


async def test_download_rejects_bad_format(client):
    r = await client.get(f"/api/goes/xrs/download?start={_START}&end={_END}&format=xml")
    assert r.status_code == 422
