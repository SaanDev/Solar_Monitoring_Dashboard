"""Assemble detected events into causal "storylines" — pure, unit-testable.

``event_correlation`` links a single pair (flare <-> radio burst). This module
generalises that into the full space-weather causal chain: a flare triggers a
CME, whose shock drives a type-II radio burst and accelerates a solar energetic
particle (proton) event, and whose arrival at Earth ~1-4 days later drives a
geomagnetic storm. Each physically-associated pair is an edge; the connected
components of that graph are the storylines.

The CME -> storm edge is what closes the ~1-4 day Sun->Earth gap: it links a CME
to a storm whose onset lands near the CME event's ``end_time`` — which the CME
service sets to the predicted arrival (DONKI WSA-ENLIL, else the SWDash DBM
estimate). Without that arrival there is nothing to associate a storm with a CME
launched days earlier.

Pure functions (no DB, no I/O) mirroring ``event_detection`` / ``event_correlation``:
chains are computed on read from whatever events are passed in, never persisted,
so a storyline always reflects the latest re-derived event set. The service layer
turns the returned structures into API responses (and adds alert-level severity).
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta

# ── Linking windows (each edge is an ordered cause -> effect within a window) ──

# A flare and the CME it launches are near-simultaneous; the CME's catalog onset
# (first coronagraph appearance) trails the flare by up to ~an hour, so 2 h of
# slack ties them without sweeping in an unrelated eruption.
FLARE_CME_MAX_GAP = timedelta(hours=2)
# Type-III bursts ride the flare's impulsive phase (matches event_correlation).
FLARE_BURST_MAX_GAP = timedelta(minutes=30)
# Type-II bursts trace the CME-driven shock through the low corona, near launch.
CME_BURST_MAX_GAP = timedelta(hours=1)
# SEP/proton onset follows the eruption (west-limb connected) within a few hours;
# a little lead tolerance absorbs detector-timing slop.
SEP_MAX_LAG = timedelta(hours=6)
SEP_LEAD_TOLERANCE = timedelta(hours=1)
# A storm onset counts as this CME's arrival when it lands within this tolerance
# of the CME's predicted arrival (the DBM window is roughly this wide).
CME_STORM_TOLERANCE = timedelta(hours=15)
# An ongoing event's effective end for gap math (mirrors event_correlation).
ONGOING_SPAN_CAP = timedelta(hours=6)

# How far apart the earliest and latest members of one chain can sit — a fast
# flare-to-storm sequence spans the CME transit. The read window is widened by
# this so a storm still links back to a CME launched days earlier.
CHAIN_MAX_SPAN = timedelta(days=6)

STORM_TYPES = {
    "geomagnetic_storm_kp",
    "geomagnetic_storm_dst",
    "geomagnetic_storm_prediction",
}

# Causal role each event type plays in a storyline (drives UI labelling/ordering).
ROLE_BY_TYPE = {
    "xray_flare": "flare",
    "cme": "cme",
    "radio_burst": "radio_burst",
    "official_radio_burst": "radio_burst",
    "proton_event": "sep",
    "geomagnetic_storm_kp": "geomagnetic_storm",
    "geomagnetic_storm_dst": "geomagnetic_storm",
    "geomagnetic_storm_prediction": "predicted_storm",
}


def event_id(e: dict) -> str:
    """Stable id of an event (matches the ``events`` composite key / API id)."""
    return f"{e['type']}:{e['start_time'].isoformat()}"


def _end(e: dict) -> datetime:
    """Effective end of a span; an ongoing one extends ``ONGOING_SPAN_CAP``."""
    return e.get("end_time") or (e["start_time"] + ONGOING_SPAN_CAP)


def _gap(a: dict, b: dict) -> timedelta:
    """Time between two spans; zero/negative when they overlap."""
    return max(b["start_time"] - _end(a), a["start_time"] - _end(b))


def _causal_edges(events: list[dict]) -> list[tuple[dict, dict]]:
    """Directed ``(cause, effect)`` edges per the physical linking rules."""
    by_type: dict[str, list[dict]] = defaultdict(list)
    for e in events:
        by_type[e["type"]].append(e)

    flares = by_type.get("xray_flare", [])
    cmes = by_type.get("cme", [])
    bursts = by_type.get("radio_burst", [])
    protons = by_type.get("proton_event", [])
    storms = [e for e in events if e["type"] in STORM_TYPES]

    edges: list[tuple[dict, dict]] = []

    # flare -> CME (co-temporal launch)
    for f in flares:
        for c in cmes:
            if abs(c["start_time"] - f["start_time"]) <= FLARE_CME_MAX_GAP:
                edges.append((f, c))

    # flare -> radio burst (impulsive-phase type III)
    for f in flares:
        for b in bursts:
            if _gap(f, b) <= FLARE_BURST_MAX_GAP:
                edges.append((f, b))

    # CME -> radio burst (shock-driven type II near launch)
    for c in cmes:
        for b in bursts:
            if abs(b["start_time"] - c["start_time"]) <= CME_BURST_MAX_GAP:
                edges.append((c, b))

    # flare / CME -> proton (SEP onset after the eruption)
    for cause in flares + cmes:
        for p in protons:
            lag = p["start_time"] - cause["start_time"]
            if -SEP_LEAD_TOLERANCE <= lag <= SEP_MAX_LAG:
                edges.append((cause, p))

    # CME -> geomagnetic storm (onset near the CME's predicted arrival = end_time)
    for c in cmes:
        arrival = c.get("end_time")
        if arrival is None:
            continue
        for s in storms:
            if abs(s["start_time"] - arrival) <= CME_STORM_TOLERANCE:
                edges.append((c, s))

    return edges


def _token(e: dict) -> str:
    """One human-readable step in a chain summary."""
    t = e["type"]
    sev = e.get("severity")
    st = e["start_time"]
    if t == "xray_flare":
        return f"{sev or 'X-ray'} flare {st:%H:%MZ}"
    if t == "cme":
        spd = e.get("peak_value")
        return f"CME {spd:.0f} km/s" if spd else "Earth-directed CME"
    if t in ("radio_burst", "official_radio_burst"):
        return "radio burst"
    if t == "proton_event":
        return f"{sev or 'S1'} proton storm"
    if t == "geomagnetic_storm_prediction":
        return f"predicted {sev or 'storm'} {st:%b %d %H:%MZ}"
    if t in ("geomagnetic_storm_kp", "geomagnetic_storm_dst"):
        label = f"{sev} storm" if sev and sev.startswith("G") else (sev or "storm")
        return f"{label} {st:%b %d %H:%MZ}"
    return t


def summarize_chain(ordered: list[dict]) -> str:
    """Deterministic one-line storyline, e.g. ``M5.1 flare 14:03Z -> CME 1120 km/s
    -> radio burst -> S1 proton storm -> G2 storm Jul 18 06:00Z``."""
    return " → ".join(_token(e) for e in ordered)


def build_chains(events: list[dict]) -> list[dict]:
    """Group events into causal storylines (connected components of the edge graph).

    Returns one dict per multi-event chain, newest first::

        {chain_id, event_ids (causal order), roles {id: role},
         start_time, end_time, summary, members [event dicts]}

    Single, unlinked events are not storylines and are omitted. ``members`` is the
    ordered event dicts for the service layer to render; the pure module adds no
    alert-level severity (that stays in the service, defined once).
    """
    if not events:
        return []

    by_id = {event_id(e): e for e in events}
    parent = {eid: eid for eid in by_id}

    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]  # path halving
            x = parent[x]
        return x

    def union(a: str, b: str) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    for cause, effect in _causal_edges(events):
        union(event_id(cause), event_id(effect))

    comps: dict[str, list[dict]] = defaultdict(list)
    for eid, e in by_id.items():
        comps[find(eid)].append(e)

    chains: list[dict] = []
    for members in comps.values():
        if len(members) < 2:
            continue  # a lone event is not a storyline
        ordered = sorted(members, key=lambda e: e["start_time"])
        ends = [e["end_time"] for e in ordered if e.get("end_time")]
        chains.append(
            {
                "chain_id": event_id(ordered[0]),
                "event_ids": [event_id(e) for e in ordered],
                "roles": {event_id(e): ROLE_BY_TYPE.get(e["type"], "event") for e in ordered},
                "start_time": ordered[0]["start_time"],
                "end_time": max(ends) if ends else None,
                "summary": summarize_chain(ordered),
                "members": ordered,
            }
        )

    chains.sort(key=lambda c: c["start_time"], reverse=True)
    return chains


def chain_id_by_event(chains: list[dict]) -> dict[str, str]:
    """Map each member event id -> its chain_id (for annotating event reads)."""
    out: dict[str, str] = {}
    for c in chains:
        for eid in c["event_ids"]:
            out[eid] = c["chain_id"]
    return out
