"""Tests for the burst-predictor scorecard: per-day comparison math, the
service aggregation over a window, and the /api/radio/predict/scorecard route."""
from datetime import date, datetime, time, timedelta, timezone
from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient

import app.services.burst_scorecard_service as scorecard
from app.collectors.collect_burst_list import BurstEvent
from app.config import settings
from app.main import app

UTC = timezone.utc
DAY = date(2026, 7, 1)


def _row(station: str, hh: int, mm: int, prob: float, label: str = "Burst") -> dict:
    return {
        "filename": f"{station}_{hh:02d}{mm:02d}.fit.gz",
        "station": station,
        "focus": "01",
        "start_time": datetime(2026, 7, 1, hh, mm, tzinfo=UTC),
        "probability": prob,
        "predicted_label": label,
        "alert_level": "",
    }


def _corroborated_rows(hh: int = 10) -> list[dict]:
    """Rows that satisfy the corroboration filter (>=4 stations, >=2 high-conf)."""
    assert settings.radio_burst_min_stations == 4
    return [
        _row("ALASKA", hh, 0, 0.95),
        _row("BLEIEN", hh, 0, 0.93),
        _row("OOTY", hh, 5, 0.75),
        _row("ROSWELL", hh, 5, 0.80),
    ]


def _official(start_hh: int, start_mm: int, end_hh: int, end_mm: int) -> BurstEvent:
    return BurstEvent(
        date=DAY,
        start=time(start_hh, start_mm),
        end=time(end_hh, end_mm),
        type="III",
        stations=["ALASKA"],
    )


# ── Pure per-day comparison ──────────────────────────────────────────────────


def test_day_stats_matches_overlapping_official():
    stats = scorecard.day_stats(DAY, _corroborated_rows(10), [_official(10, 5, 10, 20)])
    assert stats["has_data"] is True
    assert stats["predicted_count"] == 1
    assert stats["official_count"] == 1
    assert stats["matched_official"] == 1
    assert stats["matched_predicted"] == 1


def test_day_stats_counts_misses_both_ways():
    # Predicted event at 10:00 vs an official burst at 15:00 - no overlap.
    stats = scorecard.day_stats(DAY, _corroborated_rows(10), [_official(15, 0, 15, 10)])
    assert stats["matched_official"] == 0  # official burst missed by the model
    assert stats["matched_predicted"] == 0  # predicted event is a false alarm


def test_day_stats_uncorroborated_detections_form_no_event():
    rows = [_row("ALASKA", 10, 0, 0.95), _row("BLEIEN", 10, 0, 0.93)]  # 2 stations < 4
    stats = scorecard.day_stats(DAY, rows, [])
    assert stats["burst_files"] == 2
    assert stats["predicted_count"] == 0


def test_day_stats_no_data_day():
    stats = scorecard.day_stats(DAY, [], [_official(10, 0, 10, 10)])
    assert stats["has_data"] is False
    assert stats["official_count"] == 1


# ── Service aggregation ──────────────────────────────────────────────────────


async def test_scorecard_totals_skip_days_without_data(db_session, monkeypatch):
    today = datetime.now(UTC).date()
    # Only one (non-pending) day has scanner data; today/yesterday are "pending"
    # (official list not yet published) and must stay out of the totals.
    data_day = today - timedelta(days=3)
    rows_by_day = {data_day: _corroborated_rows(10)}

    async def _fake_detections(db, start, end):
        return [
            {**r, "start_time": r["start_time"].replace(
                year=start.year, month=start.month, day=start.day)}
            for r in rows_by_day.get(start.date(), [])
        ]

    async def _fake_official(first, last):
        # An official burst on every day - only today's should enter the totals.
        return {
            first + timedelta(days=i): [
                BurstEvent(date=first + timedelta(days=i), start=time(10, 5),
                           end=time(10, 20), type="III", stations=["ALASKA"])
            ]
            for i in range((last - first).days + 1)
        }

    monkeypatch.setattr(scorecard, "detections_for_range", _fake_detections)
    monkeypatch.setattr(scorecard, "_official_by_day", _fake_official)

    resp = await scorecard.get_scorecard(db_session, days=7)
    assert resp.days == 7 and len(resp.daily) == 7
    assert resp.days_with_data == 1
    assert resp.official_total == 1          # only the day with data counts
    assert resp.recall == 1.0 and resp.precision == 1.0
    assert sum(1 for d in resp.daily if d.has_data) == 1
    # The trailing PENDING_DAYS are flagged and excluded from totals.
    assert [d.pending for d in resp.daily[-2:]] == [True, True]
    assert all(not d.pending for d in resp.daily[:-2])


# ── Official bursts over a range (timeline overlay) ─────────────────────────


async def test_official_bursts_range_flattens_and_sorts(monkeypatch):
    async def _fake_by_day(first, last):
        return {
            DAY: [_official(15, 0, 15, 10), _official(10, 5, 10, 20)],
            DAY + timedelta(days=1): [
                BurstEvent(date=DAY + timedelta(days=1), start=time(23, 50),
                           end=time(0, 10), type="II", stations=["OOTY"]),  # crosses midnight
            ],
        }

    monkeypatch.setattr(scorecard, "_official_by_day", _fake_by_day)
    resp = await scorecard.get_official_bursts_range(DAY, DAY + timedelta(days=1))
    assert [e.start_time.isoformat()[:16] for e in resp.events] == [
        "2026-07-01T10:05", "2026-07-01T15:00", "2026-07-02T23:50",
    ]
    midnight = resp.events[-1]
    assert midnight.end_time.date().isoformat() == "2026-07-03"  # rolled to next day
    assert midnight.burst_type == "II"


# ── Route ────────────────────────────────────────────────────────────────────


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


async def test_scorecard_route(client, monkeypatch):
    import app.api.routes_radio as routes_radio
    from app.schemas.radio_schema import BurstScorecardResponse

    monkeypatch.setattr(
        routes_radio,
        "get_scorecard",
        AsyncMock(return_value=BurstScorecardResponse(days=30, days_with_data=5, recall=0.8)),
    )
    r = await client.get("/api/radio/predict/scorecard?days=30")
    assert r.status_code == 200
    assert r.json()["recall"] == 0.8

    assert (await client.get("/api/radio/predict/scorecard?days=90")).status_code == 422


async def test_bursts_range_route_validates(client, monkeypatch):
    import app.api.routes_radio as routes_radio
    from app.schemas.radio_schema import OfficialBurstRangeResponse

    monkeypatch.setattr(
        routes_radio,
        "get_official_bursts_range",
        AsyncMock(return_value=OfficialBurstRangeResponse(start="2026-07-01", end="2026-07-03")),
    )
    r = await client.get("/api/radio/bursts/range?start=2026-07-01&end=2026-07-03")
    assert r.status_code == 200 and r.json()["source"] == "e-callisto"

    r = await client.get("/api/radio/bursts/range?start=2026-07-03&end=2026-07-01")
    assert r.status_code == 400
    r = await client.get("/api/radio/bursts/range?start=2026-05-01&end=2026-07-01")
    assert r.status_code == 400
