"""Tests for the solar-wind time series: NOAA header-row table parsing, the
series service slicing the 7-day feed per range, and the /api/solar-wind routes."""
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient

import app.api.routes_solar_wind as routes_solar_wind
import app.services.solar_wind_service as sw_service
from app.collectors.collect_solar_wind import parse_series_table
from app.main import app
from app.schemas.solar_wind_schema import SolarWindSeries

# Real-shaped propagated-solar-wind payload (header row; null = gap).
_PROPAGATED = [
    ["time_tag", "speed", "density", "temperature", "bx", "by", "bz", "bt",
     "vx", "vy", "vz", "propagated_time_tag"],
    ["2026-07-04T04:17:00Z", "603.7", "14.83", "102617.0", "-0.42", "-11.01",
     "-14.41", "18.28", "-602.6", "1.3", "-37.1", "2026-07-04T04:50:23Z"],
    ["2026-07-04T04:18:00Z", None, "14.83", "102617.0", "-0.42", "-11.01",
     "-14.41", "18.28", "-602.6", "1.3", "-37.1", "2026-07-04T04:51:23Z"],
]

_WANTED = {"speed": "speed", "bt": "bt", "bz": "bz"}


# ── NOAA header-row table parsing ────────────────────────────────────────────


def test_parse_propagated_series():
    points = parse_series_table(_PROPAGATED, _WANTED)
    assert len(points) == 2
    assert points[0] == {
        "time": datetime(2026, 7, 4, 4, 17, tzinfo=timezone.utc),
        "speed": 603.7,
        "bt": 18.28,
        "bz": -14.41,
    }
    assert points[1]["speed"] is None  # null value = gap, not a dropped point


def test_parse_survives_reordered_columns():
    raw = [["speed", "time_tag"], ["402.0", "2026-07-04T10:00:00Z"]]
    assert parse_series_table(raw, {"speed": "speed"})[0]["speed"] == 402.0


def test_parse_skips_bad_rows_and_headers():
    raw = [
        ["time_tag", "speed"],
        ["not-a-date", "400"],   # bad timestamp -> skipped
        "garbage",               # not a list -> skipped
        ["2026-07-04T10:00:00Z", "oops"],  # bad number -> None
    ]
    points = parse_series_table(raw, {"speed": "speed"})
    assert len(points) == 1 and points[0]["speed"] is None

    assert parse_series_table([], {"speed": "speed"}) == []
    assert parse_series_table([["time_tag", "density"]], {"speed": "speed"}) == []


# ── Series service slices the 7-day feed per range ───────────────────────────


@pytest.fixture
def no_cache(monkeypatch):
    """Neutralize Redis so tests never see (or leave) cached live data."""
    monkeypatch.setattr(sw_service, "cache_get_json", AsyncMock(return_value=None))
    monkeypatch.setattr(sw_service, "cache_set_json", AsyncMock())


def _point(hours_ago: float) -> dict:
    return {
        "time": datetime.now(timezone.utc) - timedelta(hours=hours_ago),
        "speed": 400.0 + hours_ago,
        "bt": 10.0,
        "bz": -5.0,
    }


async def test_series_service_slices_range(monkeypatch, no_cache):
    monkeypatch.setattr(
        sw_service,
        "fetch_solar_wind_series",
        AsyncMock(return_value=[_point(100), _point(30), _point(1)]),
    )

    day = await sw_service.get_solar_wind_series("1-day")
    assert day.range == "1-day" and len(day.data) == 1

    week = await sw_service.get_solar_wind_series("7-day")
    assert len(week.data) == 3
    assert week.data[-1].speed == 401.0


async def test_series_service_degrades_when_feed_fails(monkeypatch, no_cache):
    monkeypatch.setattr(
        sw_service,
        "fetch_solar_wind_series",
        AsyncMock(side_effect=RuntimeError("feed down")),
    )
    series = await sw_service.get_solar_wind_series("6-hour")
    assert series.data == []


# ── Routes ───────────────────────────────────────────────────────────────────


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


async def test_series_route_returns_series(client, monkeypatch):
    t = datetime(2026, 7, 4, 10, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(
        routes_solar_wind,
        "get_solar_wind_series",
        AsyncMock(
            return_value=SolarWindSeries(
                range="1-day",
                data=[{"time": t, "speed": 603.7, "bt": 18.28, "bz": -14.41}],
            )
        ),
    )

    r = await client.get("/api/solar-wind/series?range=1-day")
    assert r.status_code == 200
    body = r.json()
    assert body["range"] == "1-day"
    assert body["data"][0]["speed"] == 603.7
    assert body["data"][0]["bz"] == -14.41


async def test_series_route_rejects_unknown_range(client):
    r = await client.get("/api/solar-wind/series?range=30-day")
    assert r.status_code == 422
