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
    fits_filename: str | None = None  # source archive file, for raw download


class RadioLiveStation(BaseModel):
    id: str
    has_metadata: bool = False   # True if this station is in the known station catalog
    focuses: list[str] = []      # available focus codes for this station on the live day


class RadioLiveStationsResponse(BaseModel):
    date: str | None = None      # the most recent day with data (ISO), or None
    stations: list[RadioLiveStation] = []


class RadioArchiveStation(BaseModel):
    id: str
    has_metadata: bool = False   # True if this station is in the known station catalog


class RadioArchiveStationsResponse(BaseModel):
    date: str
    stations: list[RadioArchiveStation] = []


class RadioArchiveFile(BaseModel):
    filename: str
    start_time: datetime


class RadioArchiveFilesResponse(BaseModel):
    date: str
    station: str
    files: list[RadioArchiveFile] = []


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
    fits_filename: str | None = None  # source archive file, for raw download


class RadioBurstDetectionResponse(BaseModel):
    """One ML-scored e-CALLISTO segment (per-file audit view)."""
    filename: str
    station: str
    start_time: datetime
    probability: float
    predicted_label: str
    alert_level: str


class RadioBurstDetectionsResponse(BaseModel):
    date: str
    count: int = 0
    burst_count: int = 0  # how many were classified Burst
    detections: list[RadioBurstDetectionResponse] = []


# ── Burst Predictor (on-demand daily prediction vs official burst list) ───────


class BurstPredictionRequest(BaseModel):
    date: str                          # UTC date YYYY-MM-DD
    stations: list[str] = []           # empty = all stations recording that day


class PredictedDetection(BaseModel):
    station: str
    focus: str
    filename: str                      # for archive dynamic-spectrum preview
    time: str                          # HH:MM:SS UTC
    probability: float
    alert_level: str


class PredictedEvent(BaseModel):
    index: int
    start: str                         # HH:MM UTC (earliest detection)
    end: str                           # HH:MM UTC (latest detection)
    start_seconds: int
    end_seconds: int
    n_stations: int
    n_detections: int
    stations: list[str]
    max_probability: float
    alert_level: str
    matched_official: bool = False     # overlaps an official burst-list event
    detections: list[PredictedDetection] = []


class OfficialBurstCompare(BaseModel):
    start: str                         # HH:MM UTC
    end: str                           # HH:MM UTC
    burst_type: str
    stations: list[str]
    matched_prediction: bool = False   # overlaps a predicted event


class BurstPredictionResult(BaseModel):
    date: str
    stations: list[str]                # stations actually scored
    total_files: int                   # segments scored
    burst_count: int                   # files classified Burst
    event_count: int                   # predicted (clustered) events
    events: list[PredictedEvent] = []
    official_events: list[OfficialBurstCompare] = []
    official_count: int = 0
    matched_count: int = 0             # predicted events matching the official list


class BurstPredictionJob(BaseModel):
    job_id: str
    status: str                        # "running" | "done" | "error"
    scanned: int = 0
    total: int = 0
    date: str
    stations: list[str] = []
    error: str | None = None
    result: BurstPredictionResult | None = None
