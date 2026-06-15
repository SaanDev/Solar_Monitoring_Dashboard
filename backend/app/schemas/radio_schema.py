from datetime import datetime
from pydantic import BaseModel


class RadioStationResponse(BaseModel):
    id: str
    name: str
    location: str
    freq_min_mhz: float
    freq_max_mhz: float
    active: bool


class RadioSpectrumResponse(BaseModel):
    station: str
    start_time: datetime | None = None
    end_time: datetime | None = None
    freq_min_mhz: float
    freq_max_mhz: float
    image_url: str
    processing_method: str


class BurstCandidateResponse(BaseModel):
    id: str
    start_time: datetime
    end_time: datetime
    freq_start_mhz: float
    freq_end_mhz: float
    classification: str
    confidence: float
    status: str = "pending"


class BurstEventSummary(BaseModel):
    index: int
    date: str
    start: str            # HH:MM UTC
    end: str              # HH:MM UTC
    burst_type: str
    stations: list[str]
    station_used: str | None = None  # station whose FITS will be shown
    has_fits: bool = False


class BurstEventsResponse(BaseModel):
    date: str | None = None
    count: int = 0
    sri_lanka_count: int = 0
    events: list[BurstEventSummary] = []


class BurstSpectrumResponse(BaseModel):
    index: int
    date: str
    start: str
    end: str
    burst_type: str
    station_used: str
    stations: list[str]
    start_time: datetime | None = None
    end_time: datetime | None = None
    freq_min_mhz: float
    freq_max_mhz: float
    image_url: str
    processing_method: str
