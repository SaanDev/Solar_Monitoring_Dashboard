import datetime as dt

from pydantic import BaseModel


class SunspotLatest(BaseModel):
    # `dt.date` (not a bare `date` import) so the field name doesn't shadow the type.
    date: dt.date | None = None
    number: float | None = None   # estimated international sunspot number (EISN)
    source: str = "silso-eisn"


class SunspotSeriesPoint(BaseModel):
    date: dt.date
    number: float                     # observed sunspot number (monthly or daily)
    smoothed: float | None = None     # 13-month smoothed SSN (cycle scope only)


class SunspotSeriesResponse(BaseModel):
    # "cycle" = long-term monthly + smoothed (NOAA indices);
    # "recent" = recent daily (SILSO daily total).
    scope: str
    source: str
    data: list[SunspotSeriesPoint]
