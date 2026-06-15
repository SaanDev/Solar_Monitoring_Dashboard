"""GOES proton flux service — live NOAA integral proton flux.

Matches the NOAA GOES Proton Flux product. The standard channels plotted are
the integral fluxes >=10 MeV, >=50 MeV and >=100 MeV (particles / cm^2 s sr).
"""
from datetime import datetime

from app.collectors.collect_goes_proton import fetch_goes_proton_json, parse_goes_proton
from app.processing.noaa_range import pick_range_file
from app.processing.storm_scale import storm_scale, PROTON_EVENT_THRESHOLD_PFU
from app.schemas.goes_schema import GoesProtonPoint, GoesProtonResponse, GoesProtonLatest

# Exact NOAA energy labels (avoid substring collisions like ">=10" in ">=100 MeV").
_GT10 = ">=10 MeV"
_GT50 = ">=50 MeV"
_GT100 = ">=100 MeV"


def _bucket_rows(rows: list[dict], start: datetime, end: datetime):
    buckets: dict[datetime, dict] = {}
    satellite = None
    for r in rows:
        t = r["time"]
        if not (start <= t <= end):
            continue
        if satellite is None and r.get("satellite") is not None:
            satellite = r["satellite"]
        b = buckets.setdefault(t, {})
        energy = r.get("energy", "")
        if energy == _GT10:
            b["gt10"] = r["flux"]
        elif energy == _GT50:
            b["gt50"] = r["flux"]
        elif energy == _GT100:
            b["gt100"] = r["flux"]
    return buckets, satellite


async def get_goes_proton(start: datetime, end: datetime) -> GoesProtonResponse:
    range_file = pick_range_file(start, end)
    raw = await fetch_goes_proton_json(range_file)
    rows = parse_goes_proton(raw)
    buckets, satellite = _bucket_rows(rows, start, end)

    points = [
        GoesProtonPoint(
            time=t,
            flux_gt10=v.get("gt10"),
            flux_gt50=v.get("gt50"),
            flux_gt100=v.get("gt100"),
        )
        for t, v in sorted(buckets.items())
    ]
    return GoesProtonResponse(start=start, end=end, satellite=satellite, data=points)


async def get_goes_proton_latest() -> GoesProtonLatest:
    """Most recent integral proton reading with NOAA S-scale + event flag."""
    raw = await fetch_goes_proton_json("6-hour")
    rows = parse_goes_proton(raw)
    if not rows:
        return GoesProtonLatest()

    def latest_for(label: str):
        candidates = [r for r in rows if r["energy"] == label]
        return max(candidates, key=lambda r: r["time"], default=None)

    l10, l50, l100 = latest_for(_GT10), latest_for(_GT50), latest_for(_GT100)
    flux10 = l10["flux"] if l10 else None
    ref = l10 or l50 or l100
    return GoesProtonLatest(
        time=ref["time"] if ref else None,
        satellite=ref.get("satellite") if ref else None,
        flux_gt10=flux10,
        flux_gt50=l50["flux"] if l50 else None,
        flux_gt100=l100["flux"] if l100 else None,
        storm_scale=storm_scale(flux10),
        event_in_progress=flux10 is not None and flux10 >= PROTON_EVENT_THRESHOLD_PFU,
    )
