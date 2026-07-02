"""Fetch the hourly Dst index from the WDC for Geomagnetism, Kyoto.

NOAA does not produce Dst, so we use Kyoto's real-time (quicklook) service:
https://wdc.kugi.kyoto-u.ac.jp/dst_realtime/

Each month is a fixed-width WDC-format file, one line per day, 24 hourly values:
    DSTyymm*DD RRX020  <base> h00 h01 ... h23 <daily-mean>
Missing values are encoded as 9999/99999.
"""
from datetime import datetime, timezone
import re
import httpx

from app.config import settings

_ROOT = "https://wdc.kugi.kyoto-u.ac.jp"
# Kyoto serves Dst in three quality tiers (same WDC text format): real-time
# quicklook (current months), provisional (recent past), final (older, definitive).
_TIERS = ("dst_realtime", "dst_provisional", "dst_final")
# Matches "DST" + yy + mm + marker + dd. The version field after the day differs
# by tier (real-time "RRX020", final "  X220"), so we don't constrain it here; the
# fixed 16-char header is skipped during parsing and the 25-number check rejects junk.
_LINE_RE = re.compile(r"^DST(\d{2})(\d{2}).?(\d{2})")
_MISSING = {9999, 99999, -9999}


def _dst_tiers_for(year: int, month: int) -> tuple[str, ...]:
    """Order tiers by likelihood for the month's age: recent → real-time first,
    older → final first. All tiers are tried as a fallback regardless."""
    now = datetime.now(timezone.utc)
    age_months = (now.year * 12 + now.month) - (year * 12 + month)
    if age_months <= 2:
        return ("dst_realtime", "dst_provisional", "dst_final")
    return ("dst_final", "dst_provisional", "dst_realtime")


def _dst_url(tier: str, year: int, month: int) -> str:
    yymm = f"{year % 100:02d}{month:02d}"
    return f"{_ROOT}/{tier}/{year}{month:02d}/dst{yymm}.for.request"


async def fetch_dst_month(year: int, month: int) -> str:
    """Fetch a month of Dst, trying quality tiers until one returns WDC data."""
    async with httpx.AsyncClient(timeout=30) as client:
        for tier in _dst_tiers_for(year, month):
            try:
                r = await client.get(_dst_url(tier, year, month))
                r.raise_for_status()
                if r.text.lstrip().startswith("DST"):  # valid WDC-format content
                    return r.text
            except Exception:
                continue
    raise RuntimeError(f"No Dst data available for {year}-{month:02d}")


def parse_dst(text: str) -> list[dict]:
    out: list[dict] = []
    for line in text.splitlines():
        m = _LINE_RE.match(line)
        if not m:
            continue
        yy, mm, dd = int(m.group(1)), int(m.group(2)), int(m.group(3))
        year = 2000 + yy
        # All signed integers after the RRX header token.
        nums = [int(n) for n in re.findall(r"-?\d+", line[16:])]
        if len(nums) < 25:
            continue
        # nums = [base, h00..h23, (daily mean)]; take the 24 hourly values.
        hourly = nums[1:25]
        for hour, val in enumerate(hourly):
            if val in _MISSING:
                continue
            ts = datetime(year, mm, dd, hour, tzinfo=timezone.utc)
            out.append({"time": ts, "dst": float(val)})
    return out
