"""Tests for the event/alert engine: pure detectors, the detect-and-store pass
(idempotency), range queries, alert derivation, cross-type correlation, and the
API endpoints."""
from datetime import datetime, timedelta, timezone

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.models.timeseries import DstIndex, GoesProton, GoesXrs, KpIndex
from app.processing.event_correlation import correlate_events, event_key
from app.processing.event_detection import (
    detect_dst_storms,
    detect_kp_storms,
    detect_proton_events,
    detect_xray_flares,
)
from app.repositories.event_repo import query_range as query_events, upsert_events
from app.repositories.timeseries_repo import upsert_points
from app.services.event_service import (
    detect_and_store,
    get_event_chains,
    get_events,
    get_latest_alerts,
)

_T0 = datetime(2026, 6, 1, 0, 0, tzinfo=timezone.utc)
_MIN = timedelta(minutes=1)


def _xrs(base: datetime, fluxes: list[float], step: timedelta = _MIN) -> list[dict]:
    return [
        {"time": base + step * i, "long_channel": f, "short_channel": None, "satellite": 18}
        for i, f in enumerate(fluxes)
    ]


# ── Pure detectors ───────────────────────────────────────────────────────────


def test_flare_detection_span_class_and_bounds():
    flares = detect_xray_flares(_xrs(_T0, [1e-7, 2e-6, 8e-6, 3e-6, 1e-7]))
    assert len(flares) == 1
    f = flares[0]
    assert f["type"] == "xray_flare"
    assert f["severity"] == "C8.0"
    assert f["peak_value"] == 8e-6
    assert f["start_time"] == _T0 + _MIN          # first sample >= C1.0
    assert f["end_time"] == _T0 + 3 * _MIN        # last active before dropping out
    assert f["peak_time"] == _T0 + 2 * _MIN


def test_flare_below_threshold_yields_nothing():
    assert detect_xray_flares(_xrs(_T0, [1e-7, 5e-7, 9e-7])) == []


def test_ongoing_event_has_no_end_time():
    # Still above threshold at the most recent sample -> ongoing.
    flares = detect_xray_flares(_xrs(_T0, [1e-7, 2e-6, 2e-5]))
    assert len(flares) == 1
    assert flares[0]["end_time"] is None
    assert flares[0]["severity"] == "M2.0"


def test_flare_data_gap_shorter_than_max_stays_one():
    # A rising flare with a 11-min data gap (<= FLARE_MAX_GAP) mid-event stays one flare.
    pts = _xrs(_T0, [1e-7, 5e-6]) + _xrs(_T0 + 12 * _MIN, [8e-6, 3e-6, 1e-7])
    flares = detect_xray_flares(pts)
    assert len(flares) == 1
    assert flares[0]["peak_value"] == 8e-6


def test_flare_long_data_gap_splits():
    # Two separate flares an hour apart -> two events (the gap is not bridged).
    pts = _xrs(_T0, [1e-7, 5e-6, 1e-7]) + _xrs(_T0 + 60 * _MIN, [1e-7, 6e-6, 1e-7])
    assert len(detect_xray_flares(pts)) == 2


def test_flare_ends_at_half_decay_not_c1_crossing():
    # An M-flare on an elevated C-class background: with the old "flux >= C1" rule
    # this span would never end (background never drops below C1) and would read as
    # perpetually "in progress". NOAA-style, it ends once flux decays half-way from
    # the peak back to the background, and no spurious flare is raised on the flat
    # background itself.
    bg = 3e-6  # C3 background
    fluxes = [bg, bg, bg, 5e-5, 3e-5, 1.5e-5, 8e-6, 5e-6, 3.5e-6, bg]
    flares = detect_xray_flares(_xrs(_T0, fluxes))
    assert len(flares) == 1
    f = flares[0]
    assert f["severity"] == "M5.0"        # classified by absolute peak, per NOAA
    assert f["peak_value"] == 5e-5
    assert f["end_time"] is not None      # properly ended, not stuck "in progress"


def test_flat_elevated_background_is_not_a_flare():
    # A steady C3 background with no brightening is background, not a flare.
    assert detect_xray_flares(_xrs(_T0, [3e-6] * 10)) == []


def test_distinct_flares_on_shared_background_not_merged():
    # Two M-flares sharing an elevated background are two events, not one giant span.
    flares = detect_xray_flares(_xrs(_T0, [2e-6, 3e-5, 5e-6, 4e-5, 2e-6]))
    assert len(flares) == 2
    assert [f["severity"] for f in flares] == ["M3.0", "M4.0"]


def test_proton_event_scale():
    pts = [{"time": _T0 + _MIN * i, "flux_gt10": v} for i, v in enumerate([1, 150, 1])]
    events = detect_proton_events(pts)
    assert len(events) == 1
    assert events[0]["type"] == "proton_event"
    assert events[0]["severity"] == "S2"
    assert events[0]["peak_value"] == 150


def test_kp_storm_scale():
    pts = [{"time": _T0 + timedelta(hours=h), "kp": v} for h, v in enumerate([4, 6, 4])]
    events = detect_kp_storms(pts)
    assert len(events) == 1
    assert events[0]["severity"] == "G2"


def test_dst_storm_uses_minimum_as_peak():
    pts = [{"time": _T0 + timedelta(hours=h), "dst": v} for h, v in enumerate([-10, -120, -60, -10])]
    events = detect_dst_storms(pts)
    assert len(events) == 1
    assert events[0]["type"] == "geomagnetic_storm_dst"
    assert events[0]["peak_value"] == -120        # most negative
    assert events[0]["severity"] == "Intense storm"


def test_kp_possible_storm_below_g1():
    # Kp peaks at 4.3 (active conditions, below the G1 onset) -> a possible storm.
    pts = [{"time": _T0 + timedelta(hours=h), "kp": v} for h, v in enumerate([2.0, 4.3, 2.0])]
    events = detect_kp_storms(pts)
    assert len(events) == 1
    assert events[0]["type"] == "geomagnetic_storm_kp"
    assert events[0]["severity"] == "Possible storm"
    assert "Possible geomagnetic storm" in events[0]["description"]


def test_dst_possible_storm_above_moderate():
    # Dst bottoms at -40 nT (weak disturbance, above the moderate-storm onset).
    pts = [{"time": _T0 + timedelta(hours=h), "dst": v} for h, v in enumerate([-10, -40, -10])]
    events = detect_dst_storms(pts)
    assert len(events) == 1
    assert events[0]["severity"] == "Possible storm"
    assert events[0]["peak_value"] == -40
    assert "Possible geomagnetic storm" in events[0]["description"]


# ── Cross-type correlation (flare ↔ radio burst) ─────────────────────────────


def _ev(etype: str, start: datetime, end: datetime | None) -> dict:
    return {"type": etype, "start_time": start, "end_time": end}


def test_overlapping_flare_and_burst_are_related():
    flare = _ev("xray_flare", _T0, _T0 + 40 * _MIN)
    burst = _ev("radio_burst", _T0 + 10 * _MIN, _T0 + 25 * _MIN)
    related = correlate_events([flare, burst])
    assert related[event_key(flare)] == [burst]
    assert related[event_key(burst)] == [flare]


def test_burst_within_gap_after_flare_is_related():
    flare = _ev("xray_flare", _T0, _T0 + 10 * _MIN)
    burst = _ev("radio_burst", _T0 + 35 * _MIN, _T0 + 50 * _MIN)  # 25 min after flare end
    assert event_key(flare) in correlate_events([flare, burst])


def test_burst_beyond_gap_is_not_related():
    flare = _ev("xray_flare", _T0, _T0 + 10 * _MIN)
    burst = _ev("radio_burst", _T0 + 45 * _MIN, _T0 + 60 * _MIN)  # 35 min after flare end
    assert correlate_events([flare, burst]) == {}


def test_ongoing_flare_relates_to_later_burst():
    flare = _ev("xray_flare", _T0, None)  # still in progress
    burst = _ev("radio_burst", _T0 + 3 * timedelta(hours=1), _T0 + 3 * timedelta(hours=1) + 15 * _MIN)
    assert event_key(flare) in correlate_events([flare, burst])


def test_stale_ongoing_flare_does_not_relate_to_much_later_burst():
    # A row stuck "in progress" for days (never closed by the detection pass)
    # must not pair with every burst that follows — the open end is capped.
    flare = _ev("xray_flare", _T0, None)
    burst = _ev("radio_burst", _T0 + timedelta(days=6), _T0 + timedelta(days=6) + 15 * _MIN)
    assert correlate_events([flare, burst]) == {}


def test_same_type_and_unpaired_types_are_not_related():
    flare_a = _ev("xray_flare", _T0, _T0 + 10 * _MIN)
    flare_b = _ev("xray_flare", _T0 + 5 * _MIN, _T0 + 15 * _MIN)
    storm = _ev("geomagnetic_storm_kp", _T0, _T0 + 10 * _MIN)
    assert correlate_events([flare_a, flare_b, storm]) == {}


def test_flare_related_to_multiple_bursts_newest_first():
    flare = _ev("xray_flare", _T0, _T0 + 60 * _MIN)
    early = _ev("radio_burst", _T0 + 5 * _MIN, _T0 + 20 * _MIN)
    late = _ev("radio_burst", _T0 + 30 * _MIN, _T0 + 45 * _MIN)
    related = correlate_events([flare, early, late])
    assert related[event_key(flare)] == [late, early]


# ── detect_and_store + repository ────────────────────────────────────────────


def _recent(minutes_ago: int) -> datetime:
    return (datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)).replace(microsecond=0)


async def test_detect_and_store_is_idempotent(db_session):
    base = _recent(120)
    await upsert_points(db_session, GoesXrs, _xrs(base, [1e-7, 2e-6, 8e-6, 3e-6, 1e-7]), "noaa-swpc")

    n1 = await detect_and_store(db_session)
    await detect_and_store(db_session)  # second pass over the same window
    assert n1 >= 1

    rows = await query_events(db_session, base - timedelta(days=1), datetime.now(timezone.utc) + _MIN)
    flares = [r for r in rows if r["type"] == "xray_flare"]
    assert len(flares) == 1  # not duplicated


async def test_alerts_surface_ongoing_event(db_session):
    base = _recent(20)
    # Rising and still elevated at the latest sample -> ongoing M-class flare.
    await upsert_points(db_session, GoesXrs, _xrs(base, [1e-7, 2e-6, 2e-5]), "noaa-swpc")
    await detect_and_store(db_session)

    alerts = await get_latest_alerts(db_session)
    flare_alerts = [a for a in alerts if a.type == "xray_flare"]
    assert len(flare_alerts) == 1
    assert flare_alerts[0].severity == "warning"      # M -> warning
    assert "in progress" in flare_alerts[0].message


async def test_possible_geomagnetic_storm_surfaces_as_watch(db_session):
    base = _recent(180)
    kp = [{"time": base + h * timedelta(hours=1), "kp": v} for h, v in enumerate([2.0, 4.5, 2.0])]
    await upsert_points(db_session, KpIndex, kp, "gfz")
    await detect_and_store(db_session)

    alerts = [a for a in await get_latest_alerts(db_session) if a.type == "geomagnetic_storm_kp"]
    assert len(alerts) == 1
    assert alerts[0].severity == "watch"              # possible storm -> watch
    assert "Possible geomagnetic storm" in alerts[0].message


async def test_old_subsided_event_kept_in_feed(db_session):
    # The alert feed keeps the full history now: even a long-subsided event stays
    # in the feed (newest first) rather than dropping off after a few hours.
    base = _recent(600)  # ~10h ago
    await upsert_points(db_session, GoesXrs, _xrs(base, [1e-7, 2e-6, 8e-6, 3e-6, 1e-7]), "noaa-swpc")
    await detect_and_store(db_session)

    flare_alerts = [a for a in await get_latest_alerts(db_session) if a.type == "xray_flare"]
    assert len(flare_alerts) == 1
    assert "subsided" in flare_alerts[0].message

    events = await get_events(db_session, base - timedelta(days=1), datetime.now(timezone.utc) + _MIN)
    assert any(e.type == "xray_flare" for e in events)


async def test_events_and_alerts_carry_related_ids(db_session):
    # An M-class flare and a radio-burst event in the same half hour must
    # cross-reference each other on both read surfaces (events + alerts).
    base = _recent(120)
    await upsert_points(db_session, GoesXrs, _xrs(base, [1e-7, 2e-6, 2e-5, 5e-6, 1e-7]), "noaa-swpc")
    await detect_and_store(db_session)
    await upsert_events(
        db_session,
        [{
            "type": "radio_burst",
            "start_time": base + 5 * _MIN,
            "end_time": base + 20 * _MIN,
            "peak_time": base + 10 * _MIN,
            "peak_value": 0.97,
            "severity": "High-confidence burst",
            "description": "Radio burst window",
            "source_url": None,
        }],
        source="ml-model",
    )

    events = await get_events(db_session, base - timedelta(days=1), datetime.now(timezone.utc) + _MIN)
    flare = next(e for e in events if e.type == "xray_flare")
    burst = next(e for e in events if e.type == "radio_burst")
    assert burst.id in flare.related_event_ids
    assert flare.id in burst.related_event_ids

    alerts = await get_latest_alerts(db_session)
    flare_alert = next(a for a in alerts if a.type == "xray_flare")
    assert burst.id in flare_alert.related_event_ids


async def test_unrelated_event_has_empty_related_ids(db_session):
    base = _recent(120)
    await upsert_points(db_session, GoesXrs, _xrs(base, [1e-7, 2e-6, 2e-5, 5e-6, 1e-7]), "noaa-swpc")
    await detect_and_store(db_session)

    events = await get_events(db_session, base - timedelta(days=1), datetime.now(timezone.utc) + _MIN)
    flare = next(e for e in events if e.type == "xray_flare")
    assert flare.related_event_ids == []


async def test_alert_feed_is_full_history_newest_first(db_session):
    older = _recent(600)  # ~10h ago
    newer = _recent(90)   # ~1.5h ago
    await upsert_points(db_session, GoesXrs, _xrs(older, [1e-7, 2e-6, 8e-6, 1e-7]), "noaa-swpc")
    await upsert_points(db_session, GoesXrs, _xrs(newer, [1e-7, 2e-5, 1e-7]), "noaa-swpc")
    await detect_and_store(db_session)

    flares = [a for a in await get_latest_alerts(db_session) if a.type == "xray_flare"]
    assert len(flares) == 2                              # both kept (no age cutoff)
    assert flares[0].timestamp >= flares[1].timestamp    # recent one at the top


# ── Event chains (causal storylines) ─────────────────────────────────────────


async def _seed_flare_cme_storm(db_session):
    """A flare -> Earth-directed CME -> geomagnetic storm chain, timed so the CME
    'arrival' (its end_time) lands just before the storm onset. Returns the ids."""
    now = datetime.now(timezone.utc).replace(microsecond=0)
    flare_start = now - timedelta(hours=50)
    cme_start = now - timedelta(hours=49, minutes=30)
    arrival = now - timedelta(hours=2)          # CME event end_time = predicted arrival
    storm_start = now - timedelta(hours=1, minutes=30)  # within 15 h of arrival
    await upsert_events(
        db_session,
        [
            {"type": "xray_flare", "start_time": flare_start, "end_time": flare_start + 30 * _MIN,
             "peak_time": flare_start + 10 * _MIN, "peak_value": 5e-5, "severity": "M5.0",
             "description": "M5.0 flare", "source_url": None},
            {"type": "cme", "start_time": cme_start, "end_time": arrival, "peak_time": arrival,
             "peak_value": 1120.0, "severity": "G2",
             "description": "Earth-directed CME at 1120 km/s", "source_url": None},
            {"type": "geomagnetic_storm_kp", "start_time": storm_start, "end_time": None,
             "peak_time": storm_start, "peak_value": 6.0, "severity": "G2",
             "description": "Geomagnetic storm G2", "source_url": None},
        ],
    )
    return now


async def test_get_event_chains_links_flare_cme_storm(db_session):
    now = await _seed_flare_cme_storm(db_session)
    # A short recent window still returns the chain: the storm intersects it and the
    # CME/flare are pulled in from the widened (multi-day) read.
    chains = await get_event_chains(db_session, now - timedelta(hours=3), now)
    assert len(chains) == 1
    c = chains[0]
    assert [e.type for e in c.events] == ["xray_flare", "cme", "geomagnetic_storm_kp"]
    assert c.chain_id == c.events[0].id
    assert "CME 1120 km/s" in c.summary
    assert c.peak_severity == "warning"  # M-flare / G2 -> warning is the peak


async def test_get_events_stamps_chain_id(db_session):
    now = await _seed_flare_cme_storm(db_session)
    events = await get_events(db_session, now - timedelta(hours=51), now)
    flare = next(e for e in events if e.type == "xray_flare")
    storm = next(e for e in events if e.type == "geomagnetic_storm_kp")
    # Every member carries the chain's id (the flare is the chain root).
    assert flare.chain_id == flare.id
    assert storm.chain_id == flare.id


# ── API endpoints ────────────────────────────────────────────────────────────


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


def _isoz(dt: datetime) -> str:
    """UTC ISO with a Z suffix (avoids the '+' -> space query-decoding quirk)."""
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


async def test_event_chains_endpoint(client, db_session):
    now = await _seed_flare_cme_storm(db_session)
    r = await client.get(
        f"/api/event-chains?start={_isoz(now - timedelta(hours=3))}&end={_isoz(now)}"
    )
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 1
    assert [e["type"] for e in body[0]["events"]] == [
        "xray_flare", "cme", "geomagnetic_storm_kp"
    ]
    assert body[0]["roles"][body[0]["events"][1]["id"]] == "cme"


async def test_event_chains_endpoint_empty(client):
    r = await client.get("/api/event-chains")
    assert r.status_code == 200
    assert r.json() == []


async def test_events_endpoint_empty(client):
    r = await client.get("/api/events")
    assert r.status_code == 200
    assert r.json() == []


async def test_alerts_endpoint_empty(client):
    r = await client.get("/api/alerts/latest")
    assert r.status_code == 200
    assert r.json() == []


async def test_events_endpoint_returns_seeded_event(client, db_session):
    base = _recent(60)
    await upsert_points(db_session, GoesXrs, _xrs(base, [1e-7, 2e-5, 1e-7]), "noaa-swpc")
    await detect_and_store(db_session)

    r = await client.get("/api/events")
    assert r.status_code == 200
    body = r.json()
    flare = next(e for e in body if e["type"] == "xray_flare")
    assert flare["severity"] == "M2.0"
    assert flare["id"].startswith("xray_flare:")


async def test_events_endpoint_rejects_bad_range(client):
    r = await client.get("/api/events?start=2024-01-02&end=2024-01-01")
    assert r.status_code == 400
