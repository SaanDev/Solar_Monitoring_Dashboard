"""Tests for causal-chain assembly (app.processing.event_chains)."""
from datetime import datetime, timedelta, timezone

from app.processing.event_chains import (
    build_chains,
    chain_id_by_event,
    event_id,
)

UTC = timezone.utc
T0 = datetime(2026, 7, 1, 0, 0, tzinfo=UTC)
MIN = timedelta(minutes=1)
HR = timedelta(hours=1)


def _ev(etype, start, end=None, severity=None, peak_value=None):
    return {
        "type": etype,
        "start_time": start,
        "end_time": end,
        "peak_time": start,
        "peak_value": peak_value,
        "severity": severity,
    }


def _full_chain_events():
    """A flare -> CME -> type-II burst -> proton -> storm sequence."""
    flare = _ev("xray_flare", T0, T0 + 30 * MIN, "M5.1", 5.1e-5)
    burst = _ev("radio_burst", T0 + 20 * MIN, T0 + 35 * MIN, "High-confidence burst", 0.97)
    arrival = T0 + timedelta(days=2)
    cme = _ev("cme", T0 + 40 * MIN, arrival, "G2", 1120.0)
    proton = _ev("proton_event", T0 + 2 * HR, T0 + 6 * HR, "S1", 42.0)
    storm = _ev("geomagnetic_storm_kp", arrival + 3 * HR, arrival + 9 * HR, "G2", 6.0)
    return flare, burst, cme, proton, storm


# ── build_chains ─────────────────────────────────────────────────────────────


def test_full_sequence_builds_one_ordered_chain():
    flare, burst, cme, proton, storm = _full_chain_events()
    chains = build_chains([storm, proton, cme, burst, flare])  # unsorted input
    assert len(chains) == 1
    c = chains[0]
    # Members appear in causal (chronological) order.
    assert c["event_ids"] == [
        event_id(flare), event_id(burst), event_id(cme), event_id(proton), event_id(storm)
    ]
    # The chain is anchored on its earliest member.
    assert c["chain_id"] == event_id(flare)
    assert c["roles"][event_id(flare)] == "flare"
    assert c["roles"][event_id(cme)] == "cme"
    assert c["roles"][event_id(burst)] == "radio_burst"
    assert c["roles"][event_id(proton)] == "sep"
    assert c["roles"][event_id(storm)] == "geomagnetic_storm"


def test_chain_summary_is_a_narrative():
    events = list(_full_chain_events())
    c = build_chains(events)[0]
    assert " → " in c["summary"]
    assert c["summary"].startswith("M5.1 flare")
    assert "CME 1120 km/s" in c["summary"]
    assert "S1 proton storm" in c["summary"]


def test_unrelated_events_do_not_link():
    # A flare and a storm 10 days apart with no CME to bridge them -> no chain.
    flare = _ev("xray_flare", T0, T0 + 20 * MIN, "C2.0")
    storm = _ev("geomagnetic_storm_kp", T0 + timedelta(days=10), None, "G1")
    assert build_chains([flare, storm]) == []


def test_same_type_events_are_not_a_chain():
    a = _ev("xray_flare", T0, T0 + 10 * MIN, "C1.0")
    b = _ev("xray_flare", T0 + 5 * MIN, T0 + 15 * MIN, "C2.0")
    assert build_chains([a, b]) == []


def test_cme_storm_link_uses_arrival_window():
    arrival = T0 + timedelta(days=2)
    cme = _ev("cme", T0, arrival, "G2", 1000.0)
    # A storm within the arrival tolerance (< 15 h) links; one well beyond does not.
    near = _ev("geomagnetic_storm_kp", arrival + 10 * HR, arrival + 16 * HR, "G1")
    far = _ev("geomagnetic_storm_kp", arrival + 30 * HR, arrival + 36 * HR, "G1")

    linked = build_chains([cme, near])
    assert len(linked) == 1
    assert set(linked[0]["event_ids"]) == {event_id(cme), event_id(near)}

    assert build_chains([cme, far]) == []


def test_cme_without_arrival_does_not_link_storm():
    # No predicted arrival (end_time None) -> nothing to associate a storm with.
    cme = _ev("cme", T0, None, "Earth-directed", 900.0)
    storm = _ev("geomagnetic_storm_kp", T0 + timedelta(days=2), None, "G1")
    assert build_chains([cme, storm]) == []


def test_chain_id_by_event_maps_every_member():
    events = list(_full_chain_events())
    chains = build_chains(events)
    mapping = chain_id_by_event(chains)
    root = chains[0]["chain_id"]
    assert all(mapping[eid] == root for eid in chains[0]["event_ids"])


def test_empty_input():
    assert build_chains([]) == []
