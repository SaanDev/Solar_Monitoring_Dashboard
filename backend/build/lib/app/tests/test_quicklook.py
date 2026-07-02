"""Tests for the overview quick-look data: SILSO EISN parsing, the solar-wind
service combining NOAA feeds, and the summary route exposing the new fields."""
from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient

import app.api.routes_summary as routes_summary
from app.collectors.collect_sunspot import latest_eisn, parse_eisn
from app.main import app
from app.schemas.solar_wind_schema import SolarWindLatest
from app.schemas.sunspot_schema import SunspotLatest

# Real-shaped SILSO EISN rows: two settled days then a 1-station current day.
_EISN_SAMPLE = (
    "2026, 06, 15, 2026.453,  74,   8.0,  21,  31,\n"
    "2026, 06, 16, 2026.456,  79,   8.0,  20,  24,\n"
    "2026, 06, 17, 2026.459,  46,   0.0,   1,   1,\n"
)


# ── SILSO EISN parsing ───────────────────────────────────────────────────────


def test_parse_eisn_extracts_rows():
    rows = parse_eisn(_EISN_SAMPLE)
    assert len(rows) == 3
    assert rows[-1]["number"] == 46 and rows[-1]["n_calc"] == 1


def test_parse_eisn_skips_garbage_and_missing():
    text = "header,junk\n\n2026, 06, 18, 2026.46, -1, 0.0, 0, 0,\n"
    assert parse_eisn(text) == []  # short/garbage lines + the -1 "no value" row


def test_latest_eisn_prefers_settled_day():
    # The 1-station current-day estimate (46) is skipped for the last settled day.
    assert latest_eisn(parse_eisn(_EISN_SAMPLE))["number"] == 79


def test_latest_eisn_falls_back_when_none_settled():
    rows = parse_eisn("2026, 06, 17, 2026.459,  46,   0.0,   1,   1,\n")
    assert latest_eisn(rows)["number"] == 46


def test_latest_eisn_empty():
    assert latest_eisn([]) is None


# ── Solar-wind service combines the two NOAA summary feeds ────────────────────


async def test_solar_wind_service_combines_feeds(monkeypatch):
    t = datetime(2026, 6, 17, 6, 26, tzinfo=timezone.utc)
    monkeypatch.setattr(
        "app.services.solar_wind_service.fetch_solar_wind_speed",
        AsyncMock(return_value={"time": t, "speed": 418.0}),
    )
    monkeypatch.setattr(
        "app.services.solar_wind_service.fetch_solar_wind_mag",
        AsyncMock(return_value={"time": t, "bz": 6.0, "bt": 11.0}),
    )
    from app.services.solar_wind_service import get_solar_wind_latest

    sw = await get_solar_wind_latest()
    assert (sw.speed, sw.bz, sw.bt) == (418.0, 6.0, 11.0)


async def test_solar_wind_service_degrades_when_mag_fails(monkeypatch):
    monkeypatch.setattr(
        "app.services.solar_wind_service.fetch_solar_wind_speed",
        AsyncMock(return_value={"time": None, "speed": 400.0}),
    )
    monkeypatch.setattr(
        "app.services.solar_wind_service.fetch_solar_wind_mag",
        AsyncMock(side_effect=RuntimeError("feed down")),
    )
    from app.services.solar_wind_service import get_solar_wind_latest

    sw = await get_solar_wind_latest()
    assert sw.speed == 400.0 and sw.bz is None and sw.bt is None


# ── Summary route exposes the quick-look fields ──────────────────────────────


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


async def test_summary_includes_quicklook_fields(client, monkeypatch):
    # Stub the new live services; neutralize the network-touching numeric feeds so
    # the route's per-source try/except yields None for them (no real HTTP).
    monkeypatch.setattr(
        routes_summary,
        "get_solar_wind_latest",
        AsyncMock(return_value=SolarWindLatest(speed=418.0, bz=6.0, bt=11.0)),
    )
    monkeypatch.setattr(
        routes_summary,
        "get_sunspot_latest",
        AsyncMock(return_value=SunspotLatest(number=79.0)),
    )
    for name in (
        "get_goes_xrs_latest",
        "get_goes_proton_latest",
        "get_kp_latest",
        "get_dst_latest",
    ):
        monkeypatch.setattr(routes_summary, name, AsyncMock(side_effect=RuntimeError("no net")))

    r = await client.get("/api/summary/latest")
    assert r.status_code == 200
    body = r.json()
    assert body["solar_wind_speed"] == 418.0
    assert body["imf_bz"] == 6.0
    assert body["imf_bt"] == 11.0
    assert body["sunspot_number"] == 79.0
