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
from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.cache import cache_get_json, cache_set_json
from app.collectors.collect_donki import fetch_cmes
from app.config import settings
from app.processing.geomag_scale import kp_storm_scale
from app.repositories.cme_repo import query_since, upsert_cmes
from app.repositories.event_repo import delete_events_of_type_since, upsert_events
from app.repositories.status_repo import record_error, record_success
from app.schemas.forecast_schema import CmeItem, CmeListResponse

logger = logging.getLogger(__name__)

# Health name surfaced by /api/sources/status.
SOURCE_NAME = "DONKI-CME"
SOURCE = "nasa-donki"

_CME_TTL = 300


def cme_to_event(r: dict) -> dict:
    """An Earth-directed catalog record as a shared-``events``-table row.

    The event spans launch -> predicted arrival (so it reads "in progress"
    while the CME is en route and "subsided" once the arrival time passes);
    severity is the G level the ENLIL run's max predicted Kp maps to.
    """
    arrival = r.get("predicted_arrival_time")
    speed = r.get("speed")
    parts = ["Earth-directed CME"]
    if r.get("source_location"):
        parts.append(f"from {r['source_location']}")
    if speed is not None:
        parts.append(f"at {speed:.0f} km/s")
    desc = " ".join(parts)
    if arrival is not None:
        desc += f" - predicted arrival {arrival.strftime('%Y-%m-%d %H:%M')} UTC (WSA-ENLIL)"
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
        earth_directed = [r for r in records if r.get("is_earth_directed")]
        if records:
            # Reconcile: an event whose CME is no longer Earth-directed (or was
            # merged/deleted in DONKI) must not linger in the alert feed.
            await delete_events_of_type_since(
                db, "cme", start, {r["start_time"] for r in earth_directed}
            )
        await upsert_events(db, [cme_to_event(r) for r in earth_directed], source=SOURCE)
        await record_success(db, SOURCE_NAME)
        logger.info(
            "DONKI pass stored %d CMEs (%d Earth-directed)",
            len(records), len(earth_directed),
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
    resp = CmeListResponse(days=days, cmes=[CmeItem.model_validate(r) for r in rows])
    await cache_set_json(key, resp.model_dump(mode="json"), _CME_TTL)
    return resp
