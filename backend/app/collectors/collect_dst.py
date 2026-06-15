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

_BASE = "https://wdc.kugi.kyoto-u.ac.jp/dst_realtime"
# Matches "DST" + yy + mm + marker + dd, e.g. "DST2606*01" or "DST260601"
_LINE_RE = re.compile(r"^DST(\d{2})(\d{2}).?(\d{2})RRX")
_MISSING = {9999, 99999, -9999}


async def fetch_dst_month(year: int, month: int) -> str:
    yymm = f"{year % 100:02d}{month:02d}"
    url = f"{_BASE}/{year}{month:02d}/dst{yymm}.for.request"
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(url)
        r.raise_for_status()
        return r.text


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
