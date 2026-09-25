from pydantic import BaseModel


class SolarCycleObservedPoint(BaseModel):
    month: str                          # "YYYY-MM"
    ssn: float | None = None            # monthly mean sunspot number (SILSO)
    smoothed_ssn: float | None = None   # 13-month smoothed (trails ~6 months)
    f107: float | None = None           # monthly mean F10.7 (sfu)
    smoothed_f107: float | None = None


class SolarCyclePredictedPoint(BaseModel):
    month: str
    ssn: float | None = None            # NOAA/NASA panel prediction
    ssn_high: float | None = None
    ssn_low: float | None = None
    f107: float | None = None
    f107_high: float | None = None
    f107_low: float | None = None


class SolarCycleResponse(BaseModel):
    source: str = "noaa-swpc"
    cycle25_start: str = "2019-12"      # solar minimum that opened Cycle 25
    observed: list[SolarCycleObservedPoint] = []
    predicted: list[SolarCyclePredictedPoint] = []
