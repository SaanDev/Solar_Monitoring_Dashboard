from datetime import datetime
from pydantic import BaseModel


class GoesXrsPoint(BaseModel):
    time: datetime
    short_channel: float | None = None
    long_channel: float | None = None


class GoesXrsResponse(BaseModel):
    start: datetime
    end: datetime
    satellite: int | None = None
    data: list[GoesXrsPoint]


class GoesXrsLatest(BaseModel):
    time: datetime | None = None
    satellite: int | None = None
    short_channel: float | None = None
    long_channel: float | None = None
    flare_class: str | None = None


class GoesProtonPoint(BaseModel):
    time: datetime
    flux_gt10: float | None = None
    flux_gt50: float | None = None
    flux_gt100: float | None = None


class GoesProtonResponse(BaseModel):
    start: datetime
    end: datetime
    satellite: int | None = None
    data: list[GoesProtonPoint]


class GoesProtonLatest(BaseModel):
    time: datetime | None = None
    satellite: int | None = None
    flux_gt10: float | None = None
    flux_gt50: float | None = None
    flux_gt100: float | None = None
    storm_scale: str | None = None
    event_in_progress: bool = False
