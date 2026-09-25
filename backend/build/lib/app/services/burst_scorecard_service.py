"""Burst-predictor scorecard: model performance vs. the official burst list.

Aggregates, per UTC day over a trailing window, the *stored* real-time
detections (``radio_burst_detections``, written by the live scanner) into
predicted events using the same clustering + corroboration criteria as the
alert pipeline, and matches them two-way against the published e-CALLISTO
burst list. Yields the operational quality numbers:

* recall    — official bursts the model also flagged (matched / official)
* precision — model events that correspond to an official burst (matched / predicted)

Days with no scored files (scanner not running) are flagged ``has_data=False``
and excluded from the totals so dashboard downtime doesn't read as model
misses. The trailing ``PENDING_DAYS`` are likewise flagged ``pending`` and
excluded: the official list is published with a lag, so a fresh day's model
events would all read as false alarms before the humans have catalogued the
day. The official list is parsed straight from the monthly text (one fetch
per calendar month, not per day, and no per-event archive resolution).
"""
from __future__ import annotations

import logging
from datetime import date as date_cls, datetime, time as time_cls, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.cache import cache_get_json, cache_set_json
from app.collectors.collect_burst_list import BurstEvent, fetch_burst_list_text, parse_burst_list
from app.ml.registry import alert_min_probability, resolve_binary
from app.repositories.radio_detection_repo import detections_for_range
from app.schemas.radio_schema import (
    BurstScorecardResponse,
    OfficialBurstItem,
    OfficialBurstRangeResponse,
    ScorecardDay,
)
from app.services.burst_predictor_service import (
    EVENT_GAP_MINUTES,
    _detection_dict,
    _is_corroborated,
    _overlaps,
    cluster_events,
)

logger = logging.getLogger(__name__)

_TTL = 3600
_SEGMENT_SECONDS = 15 * 60  # a detection covers a whole ~15-min segment
# Most recent days whose official list is likely not yet published (they stay
# visible in the daily series but don't enter the recall/precision totals).
PENDING_DAYS = 2


def _seconds(t: time_cls) -> int:
    return t.hour * 3600 + t.minute * 60 + t.second


def day_stats(
    day: date_cls,
    rows: list[dict],
    official: list[BurstEvent],
    min_prob: float | None = None,
) -> dict:
    """Pure per-day comparison (unit-testable): stored detection rows +
    official events -> counts and two-way match totals.

    ``min_prob`` defaults to the active model's alert minimum — it has to be
    per-model, since the two binary classifiers have different thresholds and a
    single figure would score one of them unfairly.
    """
    if min_prob is None:
        min_prob = alert_min_probability(resolve_binary())
    bursts = [
        _detection_dict(r)
        for r in rows
        if r["predicted_label"] == "Burst" and float(r["probability"]) >= min_prob
    ]
    clusters = [
        c for c in cluster_events(bursts, EVENT_GAP_MINUTES) if _is_corroborated(c)
    ]
    windows = [
        (c[0]["seconds"], c[-1]["seconds"] + _SEGMENT_SECONDS) for c in clusters
    ]

    matched_official = 0
    matched_predicted: set[int] = set()
    for ev in official:
        o0, o1 = _seconds(ev.start), _seconds(ev.end)
        hit = False
        for i, (p0, p1) in enumerate(windows):
            if _overlaps(p0, p1, o0, o1):
                matched_predicted.add(i)
                hit = True
        matched_official += 1 if hit else 0

    return {
        "date": day.isoformat(),
        "has_data": len(rows) > 0,
        "scored_files": len(rows),
        "burst_files": len(bursts),
        "official_count": len(official),
        "predicted_count": len(windows),
        "matched_official": matched_official,
        "matched_predicted": len(matched_predicted),
    }


async def _official_by_day(first: date_cls, last: date_cls) -> dict[date_cls, list[BurstEvent]]:
    """Official events grouped by day — one text fetch per calendar month.

    A month whose list can't be fetched contributes no events; its days still
    appear in the scorecard (they'll simply show official_count=0).
    """
    months: set[tuple[int, int]] = set()
    d = first.replace(day=1)
    while d <= last:
        months.add((d.year, d.month))
        d = (d + timedelta(days=32)).replace(day=1)

    out: dict[date_cls, list[BurstEvent]] = {}
    for year, month in sorted(months):
        try:
            text = await fetch_burst_list_text(year, month)
        except Exception as exc:  # noqa: BLE001 - a missing month is not fatal
            logger.warning("official burst list %d-%02d unavailable: %s", year, month, exc)
            continue
        for ev in parse_burst_list(text):
            if first <= ev.date <= last:
                out.setdefault(ev.date, []).append(ev)
    return out


def _burst_item(ev: BurstEvent) -> OfficialBurstItem:
    """A parsed list entry as an absolute-time item. A rare end-before-start
    entry means the burst crossed midnight — the end rolls to the next day."""
    start = datetime.combine(ev.date, ev.start, tzinfo=timezone.utc)
    end = datetime.combine(ev.date, ev.end, tzinfo=timezone.utc)
    if end < start:
        end += timedelta(days=1)
    return OfficialBurstItem(
        start_time=start, end_time=end, burst_type=ev.type, stations=ev.stations
    )


async def get_official_bursts_range(
    first: date_cls, last: date_cls
) -> OfficialBurstRangeResponse:
    """Official e-CALLISTO burst-list events for ``[first, last]`` (timeline
    overlay). Same monthly-text parsing as the scorecard — no per-event archive
    resolution, so a 30-day window costs at most two text fetches."""
    key = f"radio:official-range:{first.isoformat()}:{last.isoformat()}"
    cached = await cache_get_json(key)
    if cached is not None:
        return OfficialBurstRangeResponse.model_validate(cached)

    by_day = await _official_by_day(first, last)
    events = sorted(
        (_burst_item(ev) for evs in by_day.values() for ev in evs),
        key=lambda e: e.start_time,
    )
    resp = OfficialBurstRangeResponse(
        start=first.isoformat(), end=last.isoformat(), events=events
    )
    if resp.events:
        await cache_set_json(key, resp.model_dump(mode="json"), _TTL)
    return resp


async def get_scorecard(db: AsyncSession, days: int) -> BurstScorecardResponse:
    # Cache per model: the window's recall/precision belongs to whichever model
    # scored it, so a model switch must not serve the previous one's figures.
    spec = resolve_binary()
    min_prob = alert_min_probability(spec)
    key = f"radio:scorecard:{days}:{spec.id}"
    cached = await cache_get_json(key)
    if cached is not None:
        return BurstScorecardResponse.model_validate(cached)

    today = datetime.now(timezone.utc).date()
    first = today - timedelta(days=days - 1)
    official = await _official_by_day(first, today)

    daily: list[dict] = []
    for i in range(days):
        day = first + timedelta(days=i)
        start = datetime(day.year, day.month, day.day, tzinfo=timezone.utc)
        rows = await detections_for_range(db, start, start + timedelta(days=1))
        stats = day_stats(day, rows, official.get(day, []), min_prob=min_prob)
        stats["pending"] = (today - day).days < PENDING_DAYS
        daily.append(stats)

    scored = [d for d in daily if d["has_data"] and not d["pending"]]
    official_total = sum(d["official_count"] for d in scored)
    predicted_total = sum(d["predicted_count"] for d in scored)
    matched_official = sum(d["matched_official"] for d in scored)
    matched_predicted = sum(d["matched_predicted"] for d in scored)

    resp = BurstScorecardResponse(
        days=days,
        days_with_data=len(scored),
        official_total=official_total,
        predicted_total=predicted_total,
        matched_official=matched_official,
        matched_predicted=matched_predicted,
        recall=(matched_official / official_total) if official_total else None,
        precision=(matched_predicted / predicted_total) if predicted_total else None,
        daily=[ScorecardDay.model_validate(d) for d in daily],
    )
    await cache_set_json(key, resp.model_dump(mode="json"), _TTL)
    return resp
