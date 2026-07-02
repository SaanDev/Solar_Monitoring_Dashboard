"""Tests for the persistence layer: upsert idempotency, range/latest queries,
cache degradation, and the DB-empty live fallback (which backfills the DB)."""
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

import app.cache as cache_mod
from app.main import app
from app.models.timeseries import GoesXrs, KpIndex
from app.repositories.timeseries_repo import query_latest, query_range, upsert_points

_T0 = datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc)


# ── Repository ──────────────────────────────────────────────────────────────


async def test_upsert_is_idempotent_and_updates(db_session):
    rec = [{"time": _T0, "satellite": 18, "short_channel": 1e-7, "long_channel": 2e-6}]
    await upsert_points(db_session, GoesXrs, rec, "noaa-swpc")
    await upsert_points(db_session, GoesXrs, rec, "noaa-swpc")  # same point again

    rows = await query_range(db_session, GoesXrs, _T0 - timedelta(hours=1), _T0 + timedelta(hours=1))
    assert len(rows) == 1  # not duplicated

    # Re-ingesting with a new value updates in place.
    rec[0]["long_channel"] = 9e-6
    await upsert_points(db_session, GoesXrs, rec, "noaa-swpc")
    rows = await query_range(db_session, GoesXrs, _T0 - timedelta(hours=1), _T0 + timedelta(hours=1))
    assert len(rows) == 1
    assert rows[0]["long_channel"] == 9e-6


async def test_query_range_is_inclusive_window(db_session):
    recs = [{"time": _T0 + timedelta(hours=h), "kp": float(h)} for h in range(5)]
    await upsert_points(db_session, KpIndex, recs, "noaa-swpc")

    rows = await query_range(
        db_session, KpIndex, _T0 + timedelta(hours=1), _T0 + timedelta(hours=3)
    )
    assert [r["kp"] for r in rows] == [1.0, 2.0, 3.0]


async def test_query_latest_returns_most_recent(db_session):
    recs = [
        {"time": _T0, "kp": 1.0},
        {"time": _T0 + timedelta(hours=1), "kp": 2.0},
    ]
    await upsert_points(db_session, KpIndex, recs, "noaa-swpc")
    row = await query_latest(db_session, KpIndex)
    assert row is not None and row["kp"] == 2.0


# ── Cache ───────────────────────────────────────────────────────────────────


async def test_cache_degrades_gracefully(monkeypatch):
    class _Boom:
        async def get(self, *_):
            raise ConnectionError("redis down")

        async def set(self, *a, **k):
            raise ConnectionError("redis down")

    monkeypatch.setattr(cache_mod, "get_client", lambda: _Boom())
    assert await cache_mod.cache_get_json("missing") is None
    await cache_mod.cache_set_json("k", {"a": 1}, 30)  # must not raise


async def test_cache_roundtrip(monkeypatch):
    store: dict[str, str] = {}

    class _Fake:
        async def get(self, k):
            return store.get(k)

        async def set(self, k, v, ex=None):
            store[k] = v

    monkeypatch.setattr(cache_mod, "get_client", lambda: _Fake())
    await cache_mod.cache_set_json("k", {"a": 1}, 30)
    assert await cache_mod.cache_get_json("k") == {"a": 1}


# ── Live fallback through the API (DB empty -> live fetch -> backfill) ────────


async def test_xrs_latest_falls_back_and_backfills(db_session):
    mock = [
        {"time_tag": "2026-06-16T00:00:00Z", "energy": "0.05-0.4nm", "flux": "3.4e-7", "satellite": 18},
        {"time_tag": "2026-06-16T00:00:00Z", "energy": "0.1-0.8nm", "flux": "5.3e-6", "satellite": 18},
    ]
    with patch(
        "app.services.goes_xrs_service.fetch_goes_xrs_json",
        new_callable=AsyncMock,
        return_value=mock,
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            r = await c.get("/api/goes/xrs/latest")

    assert r.status_code == 200
    assert r.json()["flare_class"] == "C5.3"

    # The fallback should have written the live data into the DB.
    row = await query_latest(db_session, GoesXrs)
    assert row is not None
    assert row["long_channel"] == 5.3e-6
