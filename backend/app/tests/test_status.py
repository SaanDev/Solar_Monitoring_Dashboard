import pytest
from httpx import AsyncClient, ASGITransport

from app.main import app


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


async def test_status_ok(client):
    r = await client.get("/api/status")
    assert r.status_code == 200
    body = r.json()
    assert body["service"] == "space-weather-dashboard"
    assert body["status"] == "ok"
    assert "timestamp" in body
    assert "version" in body


async def test_sources_status(client):
    r = await client.get("/api/sources/status")
    assert r.status_code == 200
    body = r.json()
    assert "sources" in body
    assert len(body["sources"]) > 0


async def test_summary_latest(client):
    r = await client.get("/api/summary/latest")
    assert r.status_code == 200
    body = r.json()
    assert "timestamp" in body
    assert "goes_xray_class" in body
