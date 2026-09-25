from datetime import datetime

from pydantic import BaseModel


class SolarWindLatest(BaseModel):
    time: datetime | None = None
    speed: float | None = None   # proton bulk speed, km/s
    bz: float | None = None      # IMF Bz component (GSM), nT
    bt: float | None = None      # IMF total field magnitude, nT
    source: str = "noaa-swpc"


class SolarWindPoint(BaseModel):
    time: datetime
    speed: float | None = None   # bulk speed, km/s
    bt: float | None = None      # IMF total field magnitude, nT
    bz: float | None = None      # IMF Bz component, nT


class SolarWindSeries(BaseModel):
    range: str
    source: str = "noaa-swpc"
    data: list[SolarWindPoint] = []
