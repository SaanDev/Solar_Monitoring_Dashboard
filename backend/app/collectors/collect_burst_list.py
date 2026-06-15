"""Fetch and parse the e-CALLISTO burst lists (Monstein / deARCE).

Source: https://soleil.i4ds.ch/solarradio/data/BurstLists/2010-yyyy_Monstein/{YYYY}/
Monthly files named e-CALLISTO_{YYYY}_{MM}.txt, tab/space separated:
    Date(YYYYMMDD)   Time(HH:MM-HH:MM)   Type   Station1, Station2, ...
"""
from dataclasses import dataclass, field
from datetime import date, datetime, time, timezone
import re
import httpx

_BASE = "https://soleil.i4ds.ch/solarradio/data/BurstLists/2010-yyyy_Monstein"
_DATE_RE = re.compile(r"^\d{8}$")
_TIME_RE = re.compile(r"^(\d{2}):(\d{2})-(\d{2}):(\d{2})$")


@dataclass
class BurstEvent:
    date: date
    start: time
    end: time
    type: str
    stations: list[str] = field(default_factory=list)

    @property
    def start_dt(self) -> datetime:
        return datetime.combine(self.date, self.start, tzinfo=timezone.utc)

    @property
    def end_dt(self) -> datetime:
        return datetime.combine(self.date, self.end, tzinfo=timezone.utc)


async def fetch_burst_list_text(year: int, month: int) -> str:
    url = f"{_BASE}/{year}/e-CALLISTO_{year}_{month:02d}.txt"
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(url)
        r.raise_for_status()
        return r.text


def parse_burst_list(text: str) -> list[BurstEvent]:
    events: list[BurstEvent] = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("Product"):
            continue
        parts = line.split(None, 3)
        if len(parts) < 3 or not _DATE_RE.match(parts[0]):
            continue
        m = _TIME_RE.match(parts[1])
        if not m:
            continue  # skips no-burst markers like ##:##-##:##
        d = datetime.strptime(parts[0], "%Y%m%d").date()
        sh, sm, eh, em = (int(g) for g in m.groups())
        try:
            start, end = time(sh, sm), time(eh, em)
        except ValueError:
            continue
        burst_type = parts[2]
        stations = (
            [s.strip() for s in parts[3].split(",") if s.strip()]
            if len(parts) > 3
            else []
        )
        events.append(BurstEvent(date=d, start=start, end=end, type=burst_type, stations=stations))
    return events


async def get_latest_burst_events() -> tuple[date | None, list[BurstEvent]]:
    """Return the most recent date present in the burst list and its events."""
    now = datetime.now(timezone.utc)
    candidates = [(now.year, now.month)]
    prev = now.replace(day=1)
    prev_month = (prev.month - 2) % 12 + 1
    prev_year = prev.year - 1 if prev.month == 1 else prev.year
    candidates.append((prev_year, prev_month))

    all_events: list[BurstEvent] = []
    for year, month in candidates:
        try:
            all_events.extend(parse_burst_list(await fetch_burst_list_text(year, month)))
        except Exception:
            continue
        if all_events:
            break  # current month had data; no need for previous month

    if not all_events:
        return None, []

    latest = max(e.date for e in all_events)
    events = sorted(
        (e for e in all_events if e.date == latest), key=lambda e: e.start
    )
    return latest, events
