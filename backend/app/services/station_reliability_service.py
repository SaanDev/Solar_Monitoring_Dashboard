"""Each e-CALLISTO station's track record, as evidence for the burst confirmation.

The multi-station confirmation (``app.processing.burst_confirmation``) weighs
every station's reading — silent, or a burst at low / mid / high confidence — by
``log(P(reading | burst) / P(reading | chance))``. This service keeps those
weights:

* **Measured daily** from the trailing ``radio_burst_reliability_days`` of stored
  detections by the active model (``measure_reliability``), persisted per station
  in ``radio_station_reliability``: the station's *score* (agreement with other
  sites beyond chance), how its readings are spread while observing (chance),
  and how they are spread during *anchor* bursts — ones the reliable stations
  (score >= ``radio_burst_min_reliability``) at other sites confirm on their own.
* **Blended with built-in priors** (``station_reliability_priors``) by sample size,
  so a fresh install confirms bursts from the first day and a station with little
  history cannot swing on noise. A station's chance rates never drop below its
  long-run rates: in a quiet spell the measured rates fall, and taking them at
  face value would lower the bar exactly when coincidences are most of what
  there is to see.
* **Overridable** from the Settings page: ``always`` gives the station's flags at
  least the weight of a typical reliable station's, ``never`` ignores it.

The effective evidence is cached in-process (``cached_evidence``) for the Burst
Predictor, which is deliberately DB-free; every live scan refreshes the cache.
"""
from __future__ import annotations

import asyncio
import logging
import math
from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.ml.registry import alert_min_probability_for, resolve_model
from app.models.station_reliability import (
    OVERRIDE_ALWAYS,
    OVERRIDE_AUTO,
    OVERRIDE_NEVER,
    OVERRIDES,
)
from app.processing.burst_confirmation import (
    DEFAULT_DUTY,
    HIGH,
    N_CATEGORIES,
    SILENT,
    ConfirmationParams,
    EvidenceTable,
    StationEvidence,
    measure_reliability,
)
from app.processing.callisto_stations import STATION_LOCATIONS, site_map
from app.processing.station_reliability_priors import POOLED_ANCHOR, POOLED_NULL, PRIORS
from app.repositories import station_reliability_repo as repo
from app.repositories.radio_detection_repo import scored_rows_for_model

logger = logging.getLogger(__name__)

# How many judged bursts the built-in score is worth when blending.
PRIOR_WEIGHT = 20
# How many anchor minutes the built-in reading spread is worth when blending,
# and how many the pooled (all-station) spread is worth inside the prior.
ANCHOR_PRIOR_WEIGHT = 200
POOLED_WEIGHT = 20
# How many observing minutes the all-station chance spread is worth (two days).
NULL_PRIOR_MINUTES = 2880
# Measured chance rates are used once the station observed for a day.
_MIN_OBSERVED_MINUTES = 1440
# Evidence per reading is clipped to this range (nats).
LLR_MIN, LLR_MAX = -4.0, 6.0
# Recompute when the stored measurement is older than this.
MAX_AGE = timedelta(hours=20)

_cache: EvidenceTable | None = None


class UnknownOverrideError(ValueError):
    """An override other than auto / always / never."""


def confirmation_params() -> ConfirmationParams:
    return ConfirmationParams(
        high_conf=settings.radio_burst_high_conf_probability,
        min_evidence=settings.radio_burst_min_evidence,
        silence_weight=settings.radio_burst_silence_weight,
        min_sites=settings.radio_burst_min_sites,
        min_observing_sites=settings.radio_burst_min_observing_sites,
        site_radius_km=settings.radio_burst_site_radius_km,
        sun_min_elevation=settings.radio_burst_sun_min_elevation,
    )


# ── Effective evidence (pure) ────────────────────────────────────────────────


def _shrunk(counts) -> list[float]:
    """Observed minutes per category, shrunk toward the all-station spread by
    ``NULL_PRIOR_MINUTES`` — a day of silence is not proof a station never flags."""
    total = sum(counts) + NULL_PRIOR_MINUTES
    return [(c + NULL_PRIOR_MINUTES * p) / total for c, p in zip(counts, POOLED_NULL)]


def _chance_spread(row: dict, measured: bool, prior_null) -> list[float] | None:
    """P(reading | chance): measured when there is a day of it, each flag
    category floored at the long-run rate; else the long-run rate."""
    live = None
    if measured and row.get("null_counts") and (row.get("observed_minutes") or 0) >= _MIN_OBSERVED_MINUTES:
        live = _shrunk(row["null_counts"])
    if prior_null is not None:
        prior_null = _shrunk(prior_null)
    if live is None and prior_null is None:
        return None
    if live is None:
        flags = list(prior_null[1:])
    elif prior_null is None:
        flags = live[1:]
    else:
        flags = [max(live[c], prior_null[c]) for c in range(1, N_CATEGORIES)]
    floor = 1e-4
    flags = [max(x, floor) for x in flags]
    spread = [max(1.0 - sum(flags), floor)] + flags   # silence is what remains
    total = sum(spread)
    return [x / total for x in spread]


def _burst_spread(row: dict, measured: bool, prior_anchor, chance: list[float]) -> list[float]:
    """P(reading | burst): anchor minutes, blended toward the built-in spread
    (itself shrunk toward the all-station spread). A station with no record at
    all gets its chance spread — no evidence either way."""
    if prior_anchor is not None:
        total = sum(prior_anchor) + POOLED_WEIGHT
        base = [(a + POOLED_WEIGHT * p) / total for a, p in zip(prior_anchor, POOLED_ANCHOR)]
    else:
        base = list(chance)
    live = row.get("anchor_counts") if measured else None
    if live and sum(live):
        total = sum(live) + ANCHOR_PRIOR_WEIGHT
        return [(a + ANCHOR_PRIOR_WEIGHT * b) / total for a, b in zip(live, base)]
    return base


def _llr(burst: list[float], chance: list[float]) -> tuple[float, float, float, float]:
    return tuple(
        float(min(LLR_MAX, max(LLR_MIN, math.log(max(b, 1e-6) / max(c, 1e-6)))))
        for b, c in zip(burst, chance)
    )


def _trusted_llr(model_id: str) -> tuple[float, ...]:
    """The evidence of a typical reliable station (median per category over the
    built-in stations that clear the score bar) — what ``always`` guarantees."""
    tables = []
    for score, null, anchor in PRIORS.get(model_id, {}).values():
        if score >= settings.radio_burst_min_reliability and sum(anchor):
            chance = _chance_spread({}, False, null)
            tables.append(_llr(_burst_spread({}, False, anchor, chance), chance))
    if not tables:
        return (0.0,) * N_CATEGORIES
    return tuple(sorted(t[c] for t in tables)[len(tables) // 2] for c in range(N_CATEGORIES))


def effective_rows(rows: dict[str, dict], model_id: str) -> list[dict]:
    """Per station: score, chance rates, evidence per reading, and its status.

    ``rows`` are the stored measurements (station -> row dict). A measurement
    made with another model is ignored — it describes that model's readings.
    """
    priors = PRIORS.get(model_id, {})
    trusted = _trusted_llr(model_id)
    out = []
    for station in sorted(set(priors) | set(rows), key=str.lower):
        row = rows.get(station) or {}
        measured = row.get("model_id") == model_id
        prior_score, prior_null, prior_anchor = priors.get(station, (None, None, None))
        n = int(row.get("judged") or 0) if measured and row.get("score") is not None else 0
        if n:
            base = prior_score if prior_score is not None else 0.0
            score = (n * row["score"] + PRIOR_WEIGHT * base) / (n + PRIOR_WEIGHT)
        else:
            score = prior_score
        chance = _chance_spread(row, measured, prior_null)
        llr = (
            _llr(_burst_spread(row, measured, prior_anchor, chance), chance)
            if chance is not None
            else (0.0,) * N_CATEGORIES
        )
        override = row.get("override") or OVERRIDE_AUTO
        if override == OVERRIDE_ALWAYS:
            llr = (llr[SILENT],) + tuple(max(a, b) for a, b in zip(llr[1:], trusted[1:]))
        votes = override == OVERRIDE_ALWAYS or (
            override == OVERRIDE_AUTO
            and score is not None
            and score >= settings.radio_burst_min_reliability
        )
        out.append(
            {
                "station": station,
                "score": score,
                "measured_score": row.get("score") if measured else None,
                "prior_score": prior_score,
                "judged": n,
                "bursts": int(row.get("bursts") or 0) if measured else 0,
                "files": int(row.get("files") or 0) if measured else 0,
                "duty": chance[HIGH] if chance is not None else None,
                "evidence": list(llr),
                "override": override,
                "excluded": override == OVERRIDE_NEVER,
                # Picks the anchor bursts the next measurement learns from.
                "votes": votes,
                "computed_at": row.get("computed_at") if measured else None,
            }
        )
    return out


def _table_from(rows: list[dict]) -> EvidenceTable:
    return EvidenceTable(
        {r["station"]: StationEvidence(llr=tuple(r["evidence"]), excluded=r["excluded"]) for r in rows}
    )


def cached_evidence() -> EvidenceTable:
    """The evidence the last DB read produced, else the built-in priors alone."""
    if _cache is not None:
        return _cache
    return _table_from(effective_rows({}, resolve_model().id))


# ── DB-backed ────────────────────────────────────────────────────────────────


async def load_evidence(db: AsyncSession) -> EvidenceTable:
    """Current evidence from the stored measurements + overrides (refreshes the
    cache). Falls back to the priors if the table cannot be read, so a schema
    problem degrades confirmation rather than stopping the burst pipeline."""
    global _cache
    try:
        rows = await repo.all_rows(db)
    except Exception as exc:  # noqa: BLE001
        await db.rollback()
        logger.warning("station reliability unavailable, using built-in priors: %s", exc)
        rows = {}
    _cache = _table_from(effective_rows(rows, resolve_model().id))
    return _cache


async def recompute(db: AsyncSession) -> int:
    """Measure every station over the trailing window; returns stations measured.

    The anchor bursts are picked by the stations that vote *now* (score bar +
    overrides), with their current chance rates."""
    model_id = resolve_model().id
    now = datetime.now(timezone.utc)
    start = now - timedelta(days=max(1, settings.radio_burst_reliability_days))
    rows = await scored_rows_for_model(db, start, now, model_id)
    current = effective_rows(await repo.all_rows(db), model_id)
    voters = {r["station"]: (r["votes"], r["duty"] or DEFAULT_DUTY) for r in current}
    measured = await asyncio.to_thread(
        measure_reliability,
        rows,
        confirmation_params(),
        alert_min_probability_for,
        STATION_LOCATIONS,
        voters,
    )
    await repo.save_measurements(
        db,
        {
            st: {
                "files": m.files,
                "bursts": m.bursts,
                "judged": m.judged,
                "confirmed": m.confirmed,
                "chance_rate": m.chance_rate,
                "score": m.score,
                "duty": m.duty,
                "observed_minutes": m.observed_minutes,
                "null_counts": list(m.null_counts),
                "anchor_counts": list(m.anchor_counts),
            }
            for st, m in measured.items()
        },
        model_id=model_id,
        computed_at=now,
    )
    await load_evidence(db)
    logger.info(
        "station reliability: measured %d stations over %d files (%s)",
        len(measured), len(rows), model_id,
    )
    return len(measured)


async def ensure_fresh(db: AsyncSession) -> bool:
    """Recompute when the stored measurement is missing, stale, or from another
    model; returns whether it ran. Never raises."""
    try:
        model_id = resolve_model().id
        rows = await repo.all_rows(db)
        times = [
            r["computed_at"] for r in rows.values()
            if r.get("model_id") == model_id and r.get("computed_at") is not None
        ]
        newest = max(times, default=None)
        if newest is not None:
            newest = newest if newest.tzinfo else newest.replace(tzinfo=timezone.utc)
            if datetime.now(timezone.utc) - newest < MAX_AGE:
                await load_evidence(db)
                return False
        await recompute(db)
        return True
    except Exception as exc:  # noqa: BLE001 - the burst pipeline must keep running
        await db.rollback()
        logger.warning("station reliability recompute failed: %s", exc)
        return False


async def set_override(db: AsyncSession, station: str, override: str) -> None:
    if override not in OVERRIDES:
        raise UnknownOverrideError(f"override must be one of {', '.join(OVERRIDES)}")
    await repo.set_override(db, station, override)
    await load_evidence(db)


async def describe(db: AsyncSession) -> dict:
    """Settings-page view: every known station with its record and weights."""
    model_id = resolve_model().id
    stored = await repo.all_rows(db)
    rows = effective_rows(stored, model_id)
    sites = site_map([r["station"] for r in rows], settings.radio_burst_site_radius_km)
    for r in rows:
        r["site"] = sites[r["station"]]
        lat_lon = STATION_LOCATIONS.get(r["station"])
        r["latitude"], r["longitude"] = lat_lon if lat_lon else (None, None)
    times = [r["computed_at"] for r in rows if r["computed_at"] is not None]
    return {
        "model_id": model_id,
        "min_reliability": settings.radio_burst_min_reliability,
        "window_days": settings.radio_burst_reliability_days,
        "min_evidence": settings.radio_burst_min_evidence,
        "silence_weight": settings.radio_burst_silence_weight,
        "high_conf_probability": settings.radio_burst_high_conf_probability,
        "min_sites": settings.radio_burst_min_sites,
        "site_radius_km": settings.radio_burst_site_radius_km,
        "computed_at": max(times, default=None),
        "stations": rows,
    }
