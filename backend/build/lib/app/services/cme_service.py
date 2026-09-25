"""CME catalog ingestion + reads (NASA DONKI, WSA-ENLIL arrival predictions).

A scheduled pass re-fetches the recent DONKI window (analyses keep being
revised after an eruption) and upserts the catalog into ``cme_events``.
Earth-directed CMEs — those with an ENLIL-predicted Earth arrival — are also
upserted as ``cme`` rows in the shared ``events`` table so they surface through
the existing alert feed, spanning launch to predicted arrival. A CME whose
revised analysis is no longer Earth-directed has its event reconciled away.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.cache import cache_get_json, cache_set_json
from app.collectors.collect_donki import fetch_cmes
from app.config import settings
from app.processing.cme_transit import arrival_window, is_geoeffective
from app.processing.geomag_scale import kp_storm_scale
from app.repositories.cme_repo import query_between, query_since, upsert_cmes
from app.repositories.event_repo import delete_events_of_type_since, upsert_events
from app.repositories.status_repo import record_error, record_success
from app.services.solar_wind_service import recent_ambient_speed
from app.schemas.forecast_schema import (
    CmeHistogramBin,
    CmeHistogramResponse,
    CmeHistoryResponse,
    CmeItem,
    CmeListResponse,
)

logger = logging.getLogger(__name__)

# Health name surfaced by /api/sources/status.
SOURCE_NAME = "DONKI-CME"
SOURCE = "nasa-donki"

_CME_TTL = 300


def enrich_cme(row: dict, w: float) -> dict:
    """Add the SWDash Drag-Based-Model transit forecast to a CME record in place.

    Works on either a DB row or a freshly-parsed DONKI record (same field names).
    ``geoeffective`` comes from the cone geometry, falling back to DONKI's own
    Earth-directed flag when direction/width are missing. The arrival window needs
    a cone ``speed`` and a launch epoch — ``time21_5`` (at the 21.5 Rs DBM launch
    height) when present, else ``start_time``.
    """
    geo = is_geoeffective(row.get("longitude"), row.get("latitude"), row.get("half_angle"))
    row["geoeffective"] = bool(geo) if geo is not None else bool(row.get("is_earth_directed"))
    row["arrival_model"] = "DBM"
    row["ambient_wind_km_s"] = w
    speed = row.get("speed")
    t0 = row.get("time21_5") or row.get("start_time")
    win = arrival_window(speed, t0, w) if (speed and t0) else None
    if win is not None:
        row["predicted_arrival_dbm"] = win["arrival_time"]
        row["arrival_earliest"] = win["arrival_earliest"]
        row["arrival_latest"] = win["arrival_latest"]
        row["impact_speed_km_s"] = win["impact_speed_km_s"]
        row["transit_hours"] = win["transit_hours"]
    return row


def cme_to_event(r: dict) -> dict:
    """An Earth-directed / geoeffective catalog record as a shared-``events`` row.

    The event spans launch -> predicted arrival — DONKI's WSA-ENLIL time when NASA
    modelled it, otherwise the SWDash DBM estimate (``enrich_cme`` must have run) —
    so it reads "in progress" while en route and "subsided" once arrival passes.
    Severity is the G level of the ENLIL run's max predicted Kp, or "Earth-directed"
    when only a DBM arrival is known. The ``end_time`` (= predicted arrival) is what
    the event-chain builder uses to link a CME to the storm it drives.
    """
    enlil = r.get("predicted_arrival_time")
    arrival = enlil or r.get("predicted_arrival_dbm")
    model = "WSA-ENLIL" if enlil else "DBM"
    speed = r.get("speed")
    parts = ["Earth-directed CME"]
    if r.get("source_location"):
        parts.append(f"from {r['source_location']}")
    if speed is not None:
        parts.append(f"at {speed:.0f} km/s")
    desc = " ".join(parts)
    if arrival is not None:
        desc += f" - predicted arrival {arrival.strftime('%Y-%m-%d %H:%M')} UTC ({model})"
    kp = r.get("predicted_kp")
    if kp is not None:
        desc += f", Kp up to {kp:.0f}"
    return {
        "type": "cme",
        "start_time": r["start_time"],
        "end_time": arrival,
        "peak_time": arrival,
        "peak_value": speed,
        "severity": kp_storm_scale(kp) or "Earth-directed",
        "description": desc,
        "source_url": r.get("catalog_link"),
    }


async def collect_and_store(db: AsyncSession) -> int:
    """Fetch the recent DONKI window, upsert the catalog + Earth-directed
    events. Never raises; a failed fetch records an error status and keeps
    the existing rows (a DONKI outage must not wipe history)."""
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=settings.cme_lookback_days)
    try:
        records = await fetch_cmes(start.date(), end.date())
    except Exception as exc:  # noqa: BLE001 - network/parse failure is non-fatal
        logger.warning("DONKI CME fetch failed: %s", exc)
        await record_error(db, SOURCE_NAME, str(exc))
        return 0

    try:
        await upsert_cmes(db, records)
        # Enrich with the DBM transit forecast so a CME reaches the alert feed even
        # without an ENLIL run (geoeffective by cone geometry, DBM arrival for the span).
        w = await recent_ambient_speed()
        for r in records:
            enrich_cme(r, w)
        directed = [r for r in records if r.get("is_earth_directed") or r.get("geoeffective")]
        if records:
            # Reconcile: an event whose CME is no longer Earth-directed/geoeffective
            # (or was merged/deleted in DONKI) must not linger in the alert feed.
            await delete_events_of_type_since(
                db, "cme", start, {r["start_time"] for r in directed}
            )
        await upsert_events(db, [cme_to_event(r) for r in directed], source=SOURCE)
        await record_success(db, SOURCE_NAME)
        logger.info(
            "DONKI pass stored %d CMEs (%d Earth-directed/geoeffective)",
            len(records), len(directed),
        )
        return len(records)
    except Exception as exc:  # noqa: BLE001 - mirrors ingest runner
        await db.rollback()
        logger.warning("DONKI CME store failed: %s", exc)
        await record_error(db, SOURCE_NAME, str(exc))
        return 0


async def get_cmes(db: AsyncSession, days: int) -> CmeListResponse:
    """Catalog entries first observed in the last ``days`` days, newest first."""
    key = f"forecast:cmes:{days}"
    cached = await cache_get_json(key)
    if cached is not None:
        return CmeListResponse.model_validate(cached)

    since = datetime.now(timezone.utc) - timedelta(days=days)
    rows = await query_since(db, since)
    w = await recent_ambient_speed()
    resp = CmeListResponse(
        days=days, cmes=[CmeItem.model_validate(enrich_cme(r, w)) for r in rows]
    )
    await cache_set_json(key, resp.model_dump(mode="json"), _CME_TTL)
    return resp


async def get_cmes_range(db: AsyncSession, start: date, end: date) -> CmeHistoryResponse:
    """Past CMEs first observed in ``[start, end]`` (inclusive UTC dates).

    The scheduler only keeps the rolling ``cme_lookback_days`` window fresh in
    the catalog, so a request reaching further back is fetched on demand from
    DONKI and upserted (idempotent) before reading. A failed on-demand fetch is
    non-fatal — we still serve whatever the catalog already holds.
    """
    key = f"forecast:cmes:history:{start.isoformat()}:{end.isoformat()}"
    cached = await cache_get_json(key)
    if cached is not None:
        return CmeHistoryResponse.model_validate(cached)

    start_dt = datetime.combine(start, time.min, tzinfo=timezone.utc)
    end_dt = datetime.combine(end, time.max, tzinfo=timezone.utc)

    retained_since = datetime.now(timezone.utc) - timedelta(days=settings.cme_lookback_days)
    if start_dt < retained_since:
        try:
            await upsert_cmes(db, await fetch_cmes(start, end))
        except Exception as exc:  # noqa: BLE001 - fall back to catalog on failure
            logger.warning("on-demand DONKI history fetch failed: %s", exc)

    rows = await query_between(db, start_dt, end_dt)
    w = await recent_ambient_speed()
    resp = CmeHistoryResponse(
        start=start_dt,
        end=end_dt,
        cmes=[CmeItem.model_validate(enrich_cme(r, w)) for r in rows],
    )
    await cache_set_json(key, resp.model_dump(mode="json"), _CME_TTL)
    return resp


async def get_cme_histogram(
    db: AsyncSession, start: date, end: date, interval_days: int
) -> CmeHistogramResponse:
    """CME counts bucketed into ``interval_days``-wide bins across ``[start, end]``.

    Reuses :func:`get_cmes_range` (so old periods are fetched on demand), then
    buckets by launch date. Empty bins are kept so the histogram bars stay
    evenly spaced across the whole period.
    """
    history = await get_cmes_range(db, start, end)

    span_days = (end - start).days + 1  # inclusive
    n_bins = -(-span_days // interval_days)  # ceil division
    bins = [
        CmeHistogramBin(
            bin_start=datetime.combine(
                start + timedelta(days=i * interval_days), time.min, tzinfo=timezone.utc
            )
        )
        for i in range(n_bins)
    ]
    for c in history.cmes:
        idx = (c.start_time.date() - start).days // interval_days
        if 0 <= idx < n_bins:
            bins[idx].count += 1
            if c.is_earth_directed:
                bins[idx].earth_directed += 1

    return CmeHistogramResponse(
        start=history.start, end=history.end, interval_days=interval_days, bins=bins
    )
