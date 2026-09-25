"""Per-parameter activity histograms for the alerts page.

Buckets each space-weather parameter (solar flares, radio bursts — official &
model, CMEs, geomagnetic storms) into a shared, time-aligned set of bins so the
alerts page can render stacked small-multiples and the researcher can eyeball
temporal correlation between them. Counts are split by each parameter's natural
severity categories (flare class, burst confidence/type, G-scale, …).

Sources: the derived ``events`` table (flares, model bursts, geomagnetic
storms), the DONKI CME catalog (via :func:`get_cme_histogram`, all CMEs), and
the e-CALLISTO official burst list. Events are only present for the period the
detector has actually run, so early bins in a long period may read empty.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.cache import cache_get_json, cache_set_json
from app.repositories.event_repo import query_range
from app.schemas.alert_schema import ActivityHistogramResponse, ActivityHistogramSeries
from app.services.burst_scorecard_service import get_official_bursts_range
from app.services.cme_service import get_cme_histogram

_TTL = 300

# ── Severity/category orderings (low → high where applicable) ─────────────────
FLARE_ORDER = ["A", "B", "C", "M", "X"]
RADIO_MODEL_ORDER = ["Possible burst", "Likely burst", "High-confidence burst"]
GEOMAG_ORDER = ["Active", "G1", "G2", "G3", "G4", "G5"]
OFFICIAL_ORDER = [
    "Type II", "Type III", "Type IV", "Type V", "Type VI", "Type VII", "Type I", "Other"
]

# Dst intensity → nearest G-scale bucket so Kp- and Dst-derived storms share a
# single ordered severity axis (approximate: Dst has no exact G mapping).
_DST_TO_G = {
    "Super storm": "G5",
    "Intense storm": "G4",
    "Moderate storm": "G2",
    "Possible storm": "Active",
    "Weak storm": "Active",
}


def _as_utc(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _flare_cat(sev: str | None) -> str | None:
    c = (sev or "")[:1].upper()
    return c if c in FLARE_ORDER else None


def _radio_model_cat(sev: str | None) -> str | None:
    return sev if sev in RADIO_MODEL_ORDER else None


def _geomag_cat(sev: str | None) -> str | None:
    if not sev:
        return None
    if len(sev) == 2 and sev[0] == "G" and sev[1].isdigit():
        return sev
    return _DST_TO_G.get(sev, "Active")


def _official_cat(burst_type: str | None) -> str:
    t = (burst_type or "").upper().lstrip()
    # Longer numerals first so "III" isn't shadowed by "II" / "I".
    for roman in ("VII", "VI", "IV", "III", "II", "V", "I"):
        if t.startswith(roman):
            return f"Type {roman}"
    return "Other"


def _bin_index(dt: datetime, start: date, interval_days: int) -> int:
    return (_as_utc(dt).date() - start).days // interval_days


def _pack(key: str, label: str, order: list[str], bins: list[dict[str, int]]) -> ActivityHistogramSeries:
    """Trim ``order`` to the categories that actually occur, then emit aligned
    per-bin count rows."""
    cats = [c for c in order if any(b.get(c) for b in bins)]
    counts = [[b.get(c, 0) for c in cats] for b in bins]
    total = sum(sum(row) for row in counts)
    return ActivityHistogramSeries(
        key=key, label=label, categories=cats, counts=counts, total=total
    )


def _event_series(
    key: str,
    label: str,
    rows: list[dict],
    types: tuple[str, ...],
    cat_fn,
    order: list[str],
    start: date,
    n_bins: int,
    interval_days: int,
) -> ActivityHistogramSeries:
    bins: list[dict[str, int]] = [dict() for _ in range(n_bins)]
    for r in rows:
        if r["type"] not in types:
            continue
        idx = _bin_index(r["start_time"], start, interval_days)
        if not 0 <= idx < n_bins:
            continue
        cat = cat_fn(r.get("severity"))
        if cat is None:
            continue
        bins[idx][cat] = bins[idx].get(cat, 0) + 1
    return _pack(key, label, order, bins)


async def get_activity_histogram(
    db: AsyncSession, start: date, end: date, interval_days: int
) -> ActivityHistogramResponse:
    """Time-aligned per-parameter histograms over ``[start, end]`` in
    ``interval_days`` bins (bins oldest first)."""
    key = f"activity:hist:{start.isoformat()}:{end.isoformat()}:{interval_days}"
    cached = await cache_get_json(key)
    if cached is not None:
        return ActivityHistogramResponse.model_validate(cached)

    start_dt = datetime.combine(start, time.min, tzinfo=timezone.utc)
    end_dt = datetime.combine(end, time.max, tzinfo=timezone.utc)
    span_days = (end - start).days + 1
    n_bins = -(-span_days // interval_days)  # ceil
    bin_starts = [
        datetime.combine(
            start + timedelta(days=i * interval_days), time.min, tzinfo=timezone.utc
        )
        for i in range(n_bins)
    ]

    rows = await query_range(db, start_dt, end_dt)

    series: list[ActivityHistogramSeries] = [
        _event_series(
            "flares", "Solar flares (GOES)", rows, ("xray_flare",),
            _flare_cat, FLARE_ORDER, start, n_bins, interval_days,
        ),
    ]

    # Official radio bursts (e-CALLISTO list), bucketed by burst type.
    official = await get_official_bursts_range(start, end)
    off_bins: list[dict[str, int]] = [dict() for _ in range(n_bins)]
    for ev in official.events:
        idx = _bin_index(ev.start_time, start, interval_days)
        if 0 <= idx < n_bins:
            cat = _official_cat(ev.burst_type)
            off_bins[idx][cat] = off_bins[idx].get(cat, 0) + 1
    series.append(
        _pack("radio_official", "Radio bursts — official", OFFICIAL_ORDER, off_bins)
    )

    series.append(
        _event_series(
            "radio_model", "Radio bursts — model", rows, ("radio_burst",),
            _radio_model_cat, RADIO_MODEL_ORDER, start, n_bins, interval_days,
        )
    )

    # CMEs: reuse the DONKI histogram (all CMEs), Earth-directed stacked on top.
    cme_hist = await get_cme_histogram(db, start, end, interval_days)
    cme_counts = [[b.count - b.earth_directed, b.earth_directed] for b in cme_hist.bins]
    cme_total = sum(b.count for b in cme_hist.bins)
    series.append(
        ActivityHistogramSeries(
            key="cme",
            label="CMEs (DONKI)",
            categories=["Not Earth-directed", "Earth-directed"],
            counts=cme_counts,
            total=cme_total,
        )
    )

    series.append(
        _event_series(
            "geomagnetic", "Geomagnetic storms (Kp + Dst)", rows,
            ("geomagnetic_storm_kp", "geomagnetic_storm_dst"),
            _geomag_cat, GEOMAG_ORDER, start, n_bins, interval_days,
        )
    )

    resp = ActivityHistogramResponse(
        start=start_dt,
        end=end_dt,
        interval_days=interval_days,
        bin_starts=bin_starts,
        series=series,
    )
    await cache_set_json(key, resp.model_dump(mode="json"), _TTL)
    return resp
