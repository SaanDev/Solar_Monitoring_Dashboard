"""Tests for historical Kp (GFZ) and Dst (Kyoto tiers) retrieval."""
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

import app.services.kp_service as kp_svc
import app.services.dst_service as dst_svc
from app.collectors.collect_kp import parse_kp_gfz
from app.collectors.collect_dst import _dst_tiers_for
from app.main import app


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


# ── Pure parsing / tier selection (no network) ──


def test_parse_kp_gfz():
    data = {
        "Kp": [0.333, 1.667],
        "datetime": ["2020-01-01T00:00:00Z", "2020-01-01T03:00:00Z"],
        "status": ["def", "def"],
    }
    recs = parse_kp_gfz(data)
    assert [r["kp"] for r in recs] == [0.333, 1.667]
    assert recs[0]["time"] == datetime(2020, 1, 1, 0, 0, tzinfo=timezone.utc)


def test_parse_kp_gfz_skips_bad_rows():
    data = {"Kp": [1.0, None], "datetime": ["2020-01-01T00:00:00Z", "bad"]}
    assert len(parse_kp_gfz(data)) == 1


def test_dst_tiers_recent_vs_old():
    now = datetime.now(timezone.utc)
    assert _dst_tiers_for(now.year, now.month)[0] == "dst_realtime"
    assert _dst_tiers_for(2015, 6)[0] == "dst_final"


# ── Service routing: historical range uses the archive source ──


async def test_kp_historical_range_uses_gfz(client):
    gfz = [
        {"time": datetime(2020, 1, 1, 0, 0, tzinfo=timezone.utc), "kp": 0.333},
        {"time": datetime(2020, 1, 1, 3, 0, tzinfo=timezone.utc), "kp": 1.667},
    ]
    with patch.object(kp_svc, "fetch_kp_gfz", new=AsyncMock(return_value=gfz)) as gfz_mock, patch.object(
        kp_svc, "fetch_live_records", new=AsyncMock(return_value=[])
    ) as noaa_mock:
        r = await client.get("/api/geomagnetic/kp?start=2020-01-01T00:00:00Z&end=2020-01-02T00:00:00Z")
    assert r.status_code == 200
    body = r.json()
    assert [p["kp"] for p in body] == [0.333, 1.667]
    gfz_mock.assert_awaited()          # historical source used
    noaa_mock.assert_not_awaited()     # NOT the recent feed


async def test_dst_historical_range_refetches_kyoto(client):
    rows = [
        {"time": datetime(2015, 6, 1, 0, 0, tzinfo=timezone.utc), "dst": -8.0},
        {"time": datetime(2015, 6, 1, 1, 0, tzinfo=timezone.utc), "dst": -15.0},
    ]
    with patch.object(dst_svc, "_fetch_records", new=AsyncMock(return_value=rows)) as fetch_mock:
        r = await client.get("/api/geomagnetic/dst?start=2015-06-01T00:00:00Z&end=2015-06-02T00:00:00Z")
    assert r.status_code == 200
    body = r.json()
    assert [p["dst"] for p in body] == [-8.0, -15.0]
    fetch_mock.assert_awaited()
