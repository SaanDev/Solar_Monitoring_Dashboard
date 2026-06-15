"""GOES XRS service — fetches live NOAA data and returns structured responses.

Matches the NOAA GOES X-ray Flux product. The two channels are:
    short channel = 0.05-0.4 nm  (XRS-A / 0.5-4 Angstrom)
    long channel  = 0.1-0.8 nm   (XRS-B / 1-8 Angstrom, used for flare class)
"""
from datetime import datetime

from app.collectors.collect_goes_xrs import fetch_goes_xrs_json, parse_goes_xrs
from app.processing.flare_class import flare_class
from app.processing.noaa_range import pick_range_file
from app.schemas.goes_schema import GoesXrsPoint, GoesXrsResponse, GoesXrsLatest

_SHORT = "0.05-0.4nm"
_LONG = "0.1-0.8nm"


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
        if energy == _SHORT:
            b["short"] = r["flux"]
        elif energy == _LONG:
            b["long"] = r["flux"]
    return buckets, satellite


async def get_goes_xrs(start: datetime, end: datetime) -> GoesXrsResponse:
    range_file = pick_range_file(start, end)
    raw = await fetch_goes_xrs_json(range_file)
    rows = parse_goes_xrs(raw)
    buckets, satellite = _bucket_rows(rows, start, end)

    points = [
        GoesXrsPoint(time=t, short_channel=v.get("short"), long_channel=v.get("long"))
        for t, v in sorted(buckets.items())
    ]
    return GoesXrsResponse(start=start, end=end, satellite=satellite, data=points)


async def get_goes_xrs_latest() -> GoesXrsLatest:
    """Most recent 1-minute reading, with derived flare class (NOAA convention)."""
    raw = await fetch_goes_xrs_json("6-hour")
    rows = parse_goes_xrs(raw)
    if not rows:
        return GoesXrsLatest()

    latest_short = max((r for r in rows if r["energy"] == _SHORT), key=lambda r: r["time"], default=None)
    latest_long = max((r for r in rows if r["energy"] == _LONG), key=lambda r: r["time"], default=None)

    long_flux = latest_long["flux"] if latest_long else None
    ref = latest_long or latest_short
    return GoesXrsLatest(
        time=ref["time"] if ref else None,
        satellite=ref.get("satellite") if ref else None,
        short_channel=latest_short["flux"] if latest_short else None,
        long_channel=long_flux,
        flare_class=flare_class(long_flux),
    )
