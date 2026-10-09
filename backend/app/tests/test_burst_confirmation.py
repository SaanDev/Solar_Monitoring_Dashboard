"""Multi-station burst confirmation: the pure rule (sun, sites, evidence weighted
by each station's record), the track-record measurement and its blending with the
built-in priors, the Settings API, and the one-time re-derivation of the stored
burst history (silently, carrying the notification ledger along)."""
import math
import random
from datetime import datetime, timedelta, timezone

import pytest
from httpx import ASGITransport, AsyncClient

from app.config import settings
from app.main import app
from app.processing.burst_confirmation import (
    HIGH,
    SILENT,
    ConfirmationParams,
    EvidenceTable,
    StationEvidence,
    chance_probability,
    confirm_bursts,
    measure_reliability,
)
from app.processing.callisto_stations import site_map, sun_elevation
from app.processing.station_reliability_priors import PRIORS
from app.services import radio_burst_service as rbs
from app.services import station_reliability_service as reliability

UTC = timezone.utc
# A clean record: high flags strong, mid good, low next to nothing, silence mildly against.
_CLEAN = StationEvidence(llr=(-0.5, 0.2, 2.0, 3.0))
_TRUSTED = EvidenceTable({}, default=_CLEAN)


def _file(station, start, prob=0.97, label="Burst", model_id=None, **extra):
    return {
        "station": station, "start_time": start, "probability": prob,
        "predicted_label": label, "model_id": model_id,
        "filename": f"{station}_{start:%Y%m%d_%H%M%S}_01.fit.gz",
        "alert_level": "High-confidence burst" if prob >= 0.9 else "Likely burst",
        **extra,
    }


def _quiet(station, start):
    return _file(station, start, prob=0.03, label="No_Burst")


# ── Geometry ─────────────────────────────────────────────────────────────────


def test_sun_elevation_day_and_night():
    equinox_noon = datetime(2026, 3, 20, 12, 0, tzinfo=UTC).timestamp()
    assert sun_elevation(equinox_noon, 0.0, 0.0) > 80          # overhead at the equator
    assert sun_elevation(equinox_noon, 0.0, 180.0) < -80       # midnight on the far side
    # Sri Lanka at 07:30 local on a June morning: up; Glasgow at the same instant: not yet.
    t = datetime(2026, 6, 15, 2, 0, tzinfo=UTC).timestamp()
    assert sun_elevation(t, 7.9, 80.5) > 0
    assert sun_elevation(t, 55.9, -4.3) < 0


def test_site_map_merges_co_located_stations_only():
    sites = site_map(
        ["MEXART", "MEXICO-LANCE", "S-AFRICA-POTCHEFSTROOM", "S-AFRICA-POTCHEFSTROOM-MWA",
         "HUMAIN", "BIR", "SOMEWHERE-NEW"],
        radius_km=30,
    )
    assert sites["MEXART"] == sites["MEXICO-LANCE"]
    assert sites["S-AFRICA-POTCHEFSTROOM"] == sites["S-AFRICA-POTCHEFSTROOM-MWA"]
    assert sites["HUMAIN"] != sites["BIR"]
    assert sites["SOMEWHERE-NEW"] == "SOMEWHERE-NEW"          # unknown location: own site


def test_chance_probability_is_the_poisson_tail():
    assert chance_probability(2, 0.5) == pytest.approx(1 - math.exp(-0.5) * 1.5)
    assert chance_probability(1, 0.2) == pytest.approx(1 - math.exp(-0.2))


# ── The confirmation rule ────────────────────────────────────────────────────

_T = datetime(2026, 6, 15, 10, 0, tzinfo=UTC)  # daytime across Europe/Asia/Africa


def test_overlapping_files_confirm_inside_their_overlap():
    dets = [
        _file("STA", _T),
        _file("STB", _T + timedelta(minutes=6)),
        _quiet("STC", _T),
    ]
    res = confirm_bursts(dets, _TRUSTED, locations={})
    assert len(res.events) == 1
    ev = res.events[0]
    assert (ev.start, ev.end) == (_T + timedelta(minutes=6), _T + timedelta(minutes=15))
    assert ev.sites == ["STA", "STB"] and ev.confirming_stations == ["STA", "STB"]
    # 3 + 3 for the flags, -0.5 * 0.8 for the silent observer.
    assert ev.evidence == pytest.approx(5.6)
    assert ev.likelihood_ratio == pytest.approx(math.exp(5.6))
    assert res.unconfirmed == []


def test_a_lone_burst_is_not_confirmed():
    dets = [_file("STA", _T), _quiet("STB", _T), _quiet("STC", _T)]
    res = confirm_bursts(dets, _TRUSTED, locations={})
    assert res.events == []
    assert [d["station"] for d in res.unconfirmed] == ["STA"]


def test_too_few_observers_give_no_verdict():
    # Two agreeing stations but nobody else observing: not enough to judge chance.
    res = confirm_bursts([_file("STA", _T), _file("STB", _T)], _TRUSTED, locations={})
    assert res.events == []


def test_two_sites_must_flag_at_high_confidence():
    # Plenty of evidence from mid readings, but only one high-confidence site.
    dets = [_file("STA", _T)] + [_file(s, _T, prob=0.85) for s in ("STB", "STC", "STD")]
    assert confirm_bursts(dets, _TRUSTED, locations={}).events == []
    dets.append(_file("STE", _T))
    assert len(confirm_bursts(dets, _TRUSTED, locations={}).events) == 1


def test_noisy_stations_flag_but_carry_little_weight():
    table = EvidenceTable({"NOISY": StationEvidence(llr=(0.0, 0.0, 0.1, 0.2))}, default=_CLEAN)
    dets = [_file("STA", _T), _file("NOISY", _T), _quiet("STC", _T)]
    assert confirm_bursts(dets, table, locations={}).events == []    # 3 + 0.2 - 0.4 < 4

    dets.append(_file("STB", _T))
    ev = confirm_bursts(dets, table, locations={}).events[0]
    assert ev.confirming_stations == ["STA", "STB"]
    assert ev.also_flagged_stations == ["NOISY"]


def test_excluded_stations_are_ignored_entirely():
    table = EvidenceTable({"BAD": StationEvidence(llr=(0, 0, 3, 3), excluded=True)}, default=_CLEAN)
    dets = [_file("STA", _T), _file("BAD", _T), _quiet("STC", _T), _quiet("STD", _T)]
    res = confirm_bursts(dets, table, locations={})
    assert res.events == []                                            # BAD's flag is not a site
    assert {d["station"] for d in res.unconfirmed} == {"STA", "BAD"}


def test_co_located_stations_count_as_one_site():
    # MEXART and MEXICO-LANCE share an observatory: their agreement is one view.
    t = datetime(2026, 6, 15, 18, 0, tzinfo=UTC)  # daytime in Mexico
    dets = [_file("MEXART", t), _file("MEXICO-LANCE", t), _quiet("MEXICO-FCFM-UNACH", t),
            _quiet("MEXICO-UANL-INFIERNILLO", t)]
    assert confirm_bursts(dets, _TRUSTED).events == []
    dets[2] = _file("MEXICO-FCFM-UNACH", t)
    ev = confirm_bursts(dets, _TRUSTED).events[0]
    assert len(ev.sites) == 2 and len(ev.confirming_stations) == 3


def test_night_time_detections_do_not_count():
    european = ["HUMAIN", "BIR", "GLASGOW", "GERMANY-DLR"]
    night = datetime(2026, 1, 15, 22, 0, tzinfo=UTC)
    assert confirm_bursts([_file(s, night) for s in european], _TRUSTED).events == []
    noon = datetime(2026, 1, 15, 12, 0, tzinfo=UTC)
    assert len(confirm_bursts([_file(s, noon) for s in european], _TRUSTED).events) == 1


def test_silent_reliable_observers_count_against_a_burst():
    flagging = [_file("STA", _T), _file("STB", _T)]
    assert len(confirm_bursts(flagging + [_quiet("Q1", _T)], _TRUSTED, locations={}).events) == 1
    # The same two flags while ten clean stations watch and see nothing.
    many = [_quiet(f"Q{i}", _T) for i in range(10)]
    assert confirm_bursts(flagging + many, _TRUSTED, locations={}).events == []
    # Silence counts less when weighted down (a narrow-band receiver can miss a burst).
    lenient = ConfirmationParams(silence_weight=0.2)
    assert len(confirm_bursts(flagging + many, _TRUSTED, lenient, locations={}).events) == 1


def test_each_row_is_judged_by_its_own_models_threshold():
    minimum = {"old": 0.95, None: 0.5}.get
    dets = [_file("STA", _T, 0.93, model_id="old"), _file("STB", _T, 0.93), _quiet("STC", _T)]
    # 0.93 clears the active model's bar but not the retired one's: one flag only.
    assert confirm_bursts(dets, _TRUSTED, locations={}, burst_minimum=minimum).events == []
    assert len(confirm_bursts(dets, _TRUSTED, locations={}).events) == 1


def test_nearby_confirmed_minutes_merge_into_one_event():
    params = ConfirmationParams(merge_gap_minutes=5)
    a = [_file("STA", _T), _file("STB", _T), _quiet("STC", _T)]
    later = _T + timedelta(minutes=18)                     # 3-min gap after 10:15
    b = [_file("STA", later), _file("STB", later), _quiet("STC", later)]
    assert len(confirm_bursts(a + b, _TRUSTED, params, locations={}).events) == 1
    apart = _T + timedelta(minutes=30)
    c = [_file("STA", apart), _file("STB", apart), _quiet("STC", apart)]
    assert len(confirm_bursts(a + c, _TRUSTED, params, locations={}).events) == 2


# ── Track-record measurement ─────────────────────────────────────────────────


def _synthetic_archive(days=8, seed=1):
    """Four stations that see the same real bursts, plus one that flags at random."""
    rng = random.Random(seed)
    start = datetime(2026, 6, 1, tzinfo=UTC)
    rows = []
    for k in range(days * 96):
        t = start + timedelta(minutes=15 * k)
        real = rng.random() < 0.08
        for st in ("STA", "STB", "STC", "STD"):
            rows.append(_file(st, t) if real else _quiet(st, t))
        rows.append(_file("NOISY", t) if rng.random() < 0.25 else _quiet("NOISY", t))
    return rows


def test_reliability_separates_agreeing_stations_from_noise():
    voters = {s: (True, 0.03) for s in ("STA", "STB", "STC", "STD")}
    measured = measure_reliability(_synthetic_archive(), locations={}, voters=voters)
    assert measured["STA"].score > 0.8
    assert abs(measured["NOISY"].score) < 0.15
    assert measured["NOISY"].duty == pytest.approx(0.25, abs=0.05)
    assert measured["STA"].judged == measured["STA"].bursts > 0
    # During anchor bursts the clean stations read "high", the noisy one mostly not.
    sta, noisy = measured["STA"].anchor_counts, measured["NOISY"].anchor_counts
    assert sta[HIGH] > 0 and sta[SILENT] == 0
    assert noisy[HIGH] / sum(noisy) < 0.4
    assert sum(measured["STA"].null_counts) == measured["STA"].observed_minutes
    # No voters, no anchors.
    plain = measure_reliability(_synthetic_archive(days=2), locations={})
    assert sum(plain["STA"].anchor_counts) == 0


def test_effective_rows_blend_measurement_with_prior_and_obey_overrides(monkeypatch):
    monkeypatch.setattr(settings, "radio_burst_min_reliability", 0.15)
    model = "bnb-1.1.0"
    prior_score, prior_null, _ = PRIORS[model]["HUMAIN"]
    quiet_null = [100_000, 0, 0, 100]  # a quiet spell: flags far below the long-run rate
    rows = {
        # Measured as noise in a quiet spell: score pulled down, chance rates floored.
        "HUMAIN": {"model_id": model, "judged": 400, "score": 0.0, "observed_minutes": 100_100,
                   "null_counts": quiet_null, "anchor_counts": [5000, 0, 0, 10],
                   "override": "auto"},
        # Ignored by the operator.
        "AUSTRIA-OE3FLB": {"model_id": model, "override": "never"},
        # Boosted by the operator despite a noise-level record.
        "INDIA-OOTY": {"model_id": model, "override": "always"},
        # Measured by another model: ignored, the prior stands.
        "BIR": {"model_id": "ccm-2.0.1", "judged": 500, "score": -0.5, "override": "auto",
                "null_counts": [1, 1, 1, 1000], "observed_minutes": 2000},
        # Never seen before and no prior: no evidence either way.
        "NEW-STATION": {"model_id": model, "judged": 0, "score": None, "override": "auto"},
    }
    eff = {r["station"]: r for r in reliability.effective_rows(rows, model)}
    humain = eff["HUMAIN"]
    assert humain["score"] == pytest.approx(20 * prior_score / 420)
    assert humain["votes"] is False
    # Floored at its long-run rate (prior counts are minutes per category).
    assert humain["duty"] >= 0.95 * prior_null[HIGH] / sum(prior_null)
    assert humain["evidence"][HIGH] < 0                          # high flags were not burst-like
    assert eff["AUSTRIA-OE3FLB"]["excluded"] is True
    ooty = eff["INDIA-OOTY"]
    assert ooty["votes"] is True and ooty["evidence"][HIGH] > 1.0
    assert eff["BIR"]["score"] == PRIORS[model]["BIR"][0]
    assert eff["NEW-STATION"]["evidence"] == [0.0, 0.0, 0.0, 0.0]
    # Untouched stations keep their priors: a clean station's high flag is strong
    # evidence; a noisy one's is weak. SRI-Lanka is data-driven like the rest.
    assert eff["ALASKA-COHOE"]["evidence"][HIGH] > 1.0
    assert eff["AUSTRIA-OE3FLB"]["evidence"][HIGH] < 0.5
    assert eff["SRI-Lanka"]["excluded"] is False


def test_cached_evidence_falls_back_to_the_priors():
    table = reliability.cached_evidence()
    assert table.get("HUMAIN").llr[HIGH] > table.get("AUSTRIA-OE3FLB").llr[HIGH]
    assert table.get("NEVER-HEARD-OF").llr == (0.0, 0.0, 0.0, 0.0)


# ── Service + API ────────────────────────────────────────────────────────────


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


async def test_recompute_measures_and_keeps_overrides(db_session, monkeypatch):
    from app.repositories.radio_detection_repo import upsert_detections
    from app.repositories.station_reliability_repo import all_rows, set_override

    now = datetime.now(UTC)
    base = now - timedelta(days=5)
    rows = [
        {**r, "end_time": r["start_time"] + timedelta(minutes=15), "focus": "01",
         "model_id": "bnb-1.1.0"}
        for r in _synthetic_archive(days=3)
    ]
    shift = base - rows[0]["start_time"]
    for r in rows:
        r["start_time"] += shift
        r["end_time"] += shift
        r["filename"] = f"{r['station']}_{r['start_time']:%Y%m%d_%H%M%S}_01.fit.gz"
    await upsert_detections(db_session, rows)
    await set_override(db_session, "NOISY", "never")

    assert await reliability.recompute(db_session) == 5
    stored = await all_rows(db_session)
    assert stored["NOISY"]["override"] == "never"            # survives recomputation
    assert stored["STA"]["judged"] > 0 and stored["STA"]["score"] > 0.5
    assert len(stored["STA"]["null_counts"]) == 4
    assert reliability.cached_evidence().get("NOISY").excluded is True
    # Fresh measurement: the periodic check leaves it alone.
    assert await reliability.ensure_fresh(db_session) is False


async def test_reliability_api_lists_and_overrides(client):
    body = (await client.get("/api/radio/reliability")).json()
    by_station = {s["station"]: s for s in body["stations"]}
    assert len(by_station) >= len(PRIORS["bnb-1.1.0"])
    assert by_station["MEXART"]["site"] == by_station["MEXICO-LANCE"]["site"]
    assert len(by_station["HUMAIN"]["evidence"]) == 4
    assert body["min_evidence"] == settings.radio_burst_min_evidence

    r = await client.put("/api/radio/reliability/HUMAIN", json={"override": "never"})
    assert r.status_code == 200
    humain = next(s for s in r.json()["stations"] if s["station"] == "HUMAIN")
    assert humain["override"] == "never" and humain["excluded"] is True
    assert reliability.cached_evidence().get("HUMAIN").excluded is True

    bad = await client.put("/api/radio/reliability/HUMAIN", json={"override": "sometimes"})
    assert bad.status_code == 422


# ── History re-derivation + notification ledger ──────────────────────────────


async def test_history_is_rederived_once_and_silently(db_session, trust_all_stations):
    from app.repositories.app_settings_repo import get_or_create_settings
    from app.repositories.event_repo import query_range, upsert_events
    from app.repositories.notification_repo import sent_severities
    from app.repositories.radio_detection_repo import upsert_detections
    from app.services.event_service import event_id_for

    day = (datetime.now(UTC) - timedelta(days=3)).replace(hour=10, minute=0, second=0, microsecond=0)
    # An old-rule event that the new rule does not confirm (one station only)...
    await upsert_events(db_session, [{
        "type": "radio_burst", "start_time": day - timedelta(hours=2),
        "end_time": day - timedelta(hours=2) + timedelta(minutes=15),
        "peak_time": None, "peak_value": 0.9, "severity": "High-confidence burst",
        "description": "old rule", "source_url": None,
    }], source="ml-model")
    # ...and a burst three stations agree on.
    await upsert_detections(db_session, [
        {**_file(s, day), "end_time": day + timedelta(minutes=15), "focus": "01",
         "model_id": "bnb-1.1.0"}
        for s in ("STA", "STB", "STC")
    ] + [{**_file("LONE", day - timedelta(hours=2)), "focus": "01", "model_id": "bnb-1.1.0"}])

    assert await rbs.rederive_history_if_outdated(db_session) is True
    events = [e for e in await query_range(db_session, day - timedelta(days=1), day + timedelta(days=1))
              if e["type"] == "radio_burst"]
    assert [e["start_time"] for e in events] == [day]
    assert "old rule" not in events[0]["description"]
    assert "evidence" in events[0]["description"]
    # Re-derived history is not news: already in the ledger, so nothing is sent.
    eid = event_id_for(events[0])
    assert eid in await sent_severities(db_session, [eid])
    assert (await get_or_create_settings(db_session)).radio_burst_derivation_version == rbs.RADIO_DERIVATION_VERSION
    assert await rbs.rederive_history_if_outdated(db_session) is False


async def test_an_announced_burst_stays_announced_when_its_start_moves(db_session, trust_all_stations):
    from app.repositories.notification_repo import record_sent, sent_severities
    from app.repositories.radio_detection_repo import upsert_detections
    from app.services.event_service import event_id_for

    t = datetime.now(UTC).replace(second=0, microsecond=0) - timedelta(hours=2)
    first = [{**_file(s, t), "end_time": t + timedelta(minutes=15), "focus": "01",
              "model_id": "bnb-1.1.0"} for s in ("STA", "STB", "STC")]
    await upsert_detections(db_session, first)
    [ev] = await rbs.rebuild_radio_burst_events(db_session)
    await record_sent(db_session, [(event_id_for(ev), "warning")])

    # Late files from three more stations, starting earlier, extend the burst back.
    early = t - timedelta(minutes=8)
    await upsert_detections(db_session, [
        {**_file(s, early), "end_time": early + timedelta(minutes=15), "focus": "01",
         "model_id": "bnb-1.1.0"} for s in ("STD", "STE", "STF")
    ])
    [moved] = await rbs.rebuild_radio_burst_events(db_session)
    assert moved["start_time"] < ev["start_time"]
    new_id = event_id_for(moved)
    assert (await sent_severities(db_session, [new_id])) == {new_id: "warning"}
