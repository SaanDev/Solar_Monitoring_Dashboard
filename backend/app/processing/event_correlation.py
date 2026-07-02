"""Cross-type correlation between detected events.

Physically associated space-weather events are linked so the UI can surface
them together. Currently one association is modelled: X-ray flares and solar
radio bursts — both signatures of the same magnetic-reconnection episode, with
type-III bursts riding the flare's impulsive phase and type-II bursts following
the eruption within tens of minutes.

Pure functions (no DB, no I/O) mirroring ``event_detection``: correlation is
computed on read from whatever events are passed in, never persisted, so links
always reflect the latest re-derived event set.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta

# Two events are related when their spans overlap or the gap between them is at
# most this long. Radio bursts are aggregated into 15-minute windows, so half an
# hour of slack ties a burst window to its flare without sweeping in unrelated
# activity from elsewhere in the day.
FLARE_BURST_MAX_GAP = timedelta(minutes=30)

# An ongoing event (``end_time=None``) is open-ended, but only up to this long
# past its onset. A genuinely in-progress flare still pairs with a burst
# arriving now, while a stale row stuck "in progress" (e.g. one that fell out
# of the detection lookback before being closed) doesn't relate to everything
# that happens days later.
ONGOING_SPAN_CAP = timedelta(hours=6)

# Unordered pairs of event types that are physically associated.
RELATED_TYPE_PAIRS: set[frozenset[str]] = {frozenset({"xray_flare", "radio_burst"})}

EventKey = tuple[str, datetime]


def event_key(e: dict) -> EventKey:
    """Identity of an event dict within one correlation pass (mirrors the
    ``(type, start_time)`` composite key of the ``events`` table)."""
    return (e["type"], e["start_time"])


def _end(e: dict) -> datetime:
    """Effective end of a span; an ongoing one extends ``ONGOING_SPAN_CAP``
    past its onset (see the constant's rationale)."""
    return e.get("end_time") or (e["start_time"] + ONGOING_SPAN_CAP)


def _gap(a: dict, b: dict) -> timedelta:
    """Time between two event spans; zero or negative when they overlap."""
    return max(b["start_time"] - _end(a), a["start_time"] - _end(b))


def correlate_events(events: list[dict]) -> dict[EventKey, list[dict]]:
    """Link events of associated types that occurred together.

    Returns ``(type, start_time) -> related events (newest first)``; only events
    with at least one partner appear as keys.
    """
    by_type: dict[str, list[dict]] = defaultdict(list)
    for e in events:
        by_type[e["type"]].append(e)

    related: dict[EventKey, list[dict]] = defaultdict(list)
    for pair in RELATED_TYPE_PAIRS:
        type_a, type_b = sorted(pair)
        for a in by_type.get(type_a, []):
            for b in by_type.get(type_b, []):
                if _gap(a, b) <= FLARE_BURST_MAX_GAP:
                    related[event_key(a)].append(b)
                    related[event_key(b)].append(a)

    for partners in related.values():
        partners.sort(key=lambda e: e["start_time"], reverse=True)
    return dict(related)
