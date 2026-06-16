"""Tests for Kp/Dst archive downloads (raw CSV/JSON + rendered PNG)."""
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

import app.api.routes_geomagnetic as rg
from app.main import app
from app.schemas.geomagnetic_schema import DstPoint, KpPoint

_T0 = datetime(2025, 1, 15, 0, 0, tzinfo=timezone.utc)
_START = "2025-01-15T00:00:00Z"
_END = "2025-01-15T23:59:00Z"

_KP = [
    KpPoint(time=_T0, kp=2.0),
    KpPoint(time=_T0 + timedelta(hours=3), kp=5.3),
]
_DST = [
    DstPoint(time=_T0, dst=-12.0),
    DstPoint(time=_T0 + timedelta(hours=1), dst=-48.0),
]


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


async def test_kp_download_csv(client):
    with patch.object(rg, "get_kp", new=AsyncMock(return_value=_KP)):
        r = await client.get(f"/api/geomagnetic/kp/download?start={_START}&end={_END}&format=csv")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")
    assert "attachment" in r.headers["content-disposition"]
    assert "time,kp" in r.text
    assert "5.3" in r.text


async def test_kp_download_json(client):
    with patch.object(rg, "get_kp", new=AsyncMock(return_value=_KP)):
        r = await client.get(f"/api/geomagnetic/kp/download?start={_START}&end={_END}&format=json")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/json")
    body = r.json()
    assert isinstance(body, list) and body[1]["kp"] == 5.3


async def test_kp_plot_png(client):
    with patch.object(rg, "get_kp", new=AsyncMock(return_value=_KP)):
        inline = await client.get(f"/api/geomagnetic/kp/plot?start={_START}&end={_END}")
        dl = await client.get(f"/api/geomagnetic/kp/plot?start={_START}&end={_END}&download=1")
    assert inline.status_code == 200
    assert inline.headers["content-type"] == "image/png"
    assert inline.content[:8] == b"\x89PNG\r\n\x1a\n"
    assert "attachment" not in inline.headers.get("content-disposition", "")
    assert "attachment" in dl.headers["content-disposition"]


async def test_dst_download_csv_and_plot(client):
    with patch.object(rg, "get_dst", new=AsyncMock(return_value=_DST)):
        csv_r = await client.get(f"/api/geomagnetic/dst/download?start={_START}&end={_END}&format=csv")
        png_r = await client.get(f"/api/geomagnetic/dst/plot?start={_START}&end={_END}")
    assert csv_r.status_code == 200
    assert "time,dst_nt" in csv_r.text
    assert "-48.0" in csv_r.text
    assert png_r.status_code == 200
    assert png_r.content[:8] == b"\x89PNG\r\n\x1a\n"


async def test_download_rejects_bad_format(client):
    r = await client.get(f"/api/geomagnetic/kp/download?start={_START}&end={_END}&format=xml")
    assert r.status_code == 422
