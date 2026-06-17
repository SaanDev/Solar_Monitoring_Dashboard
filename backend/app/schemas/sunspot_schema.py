import datetime as dt

from pydantic import BaseModel


class SunspotLatest(BaseModel):
    # `dt.date` (not a bare `date` import) so the field name doesn't shadow the type.
    date: dt.date | None = None
    number: float | None = None   # estimated international sunspot number (EISN)
    source: str = "silso-eisn"
