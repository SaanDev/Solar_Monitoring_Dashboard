from datetime import datetime
from typing import Literal

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
    model_id: str = ""                 # which classifier produced this verdict
    burst_type: str | None = None      # "Type II" | "Type III" | "Other"
    type_confidence: float | None = None


class RadioBurstDetectionsResponse(BaseModel):
    date: str
    count: int = 0
    burst_count: int = 0  # how many were classified Burst
    detections: list[RadioBurstDetectionResponse] = []


# ── Model registry (which classifiers are available to run) ───────────────────


class ModelInfo(BaseModel):
    """One selectable classifier, as advertised to the UI."""
    id: str                            # "ccm-1.1.0"
    name: str                          # "CCM v1.1.0"
    full_name: str
    kind: str                          # "binary" (burst / no-burst) | "type"
    version: str
    description: str
    # False when the checkpoint is missing or still a Git LFS pointer — the UI
    # greys the option out instead of letting a run fail mid-scan.
    available: bool = True
    threshold: float | None = None     # binary models only
    classes: list[str] = []
    metrics: dict[str, float] = {}
    is_default: bool = False


class ModelsResponse(BaseModel):
    models: list[ModelInfo] = []
    default_binary: str                # id the page should preselect
    # Where `default_binary` comes from: "selected" = chosen on the Settings page
    # and stored in the database; "config" = still following the deployment's
    # RADIO_BURST_BINARY_MODEL. Lets the UI say which one is in force.
    default_binary_source: Literal["selected", "config"] = "config"
    type_model: str | None = None      # id used for the burst-type stage
    classify_types: bool = True        # server default for the type stage


class BinaryModelSelection(BaseModel):
    """PUT body: which binary classifier the automatic scan should run."""
    model_id: str                      # "ccm-1.0.0" | "ccm-1.1.0"


# ── Burst Predictor (on-demand daily prediction vs official burst list) ───────


class BurstPredictionRequest(BaseModel):
    date: str                          # UTC date YYYY-MM-DD
    stations: list[str] = []           # empty = all stations recording that day
    # False = event-selection criteria (multi-station corroboration, the live
    # alert filter). True = raw model output: every segment the model labels
    # "Burst" becomes an event, so a narrow station selection never hides bursts.
    raw: bool = False
    # Binary classifier id; null = the server default. Unlike `raw`, this changes
    # the scores, so it is fixed for the job's lifetime.
    model: str | None = None
    # Run the burst-type stage on burst-positive files; null = server default.
    classify_types: bool | None = None


class TypedRegion(BaseModel):
    """A bright region inside one segment, with its predicted burst type."""
    freq_min_mhz: float | None = None
    freq_max_mhz: float | None = None
    start_seconds: int                 # from the start of the segment
    end_seconds: int
    burst_type: str | None = None
    confidence: float | None = None
    area: int = 0                      # pixels above the brightness threshold


class PredictedDetection(BaseModel):
    station: str
    focus: str
    filename: str                      # for archive dynamic-spectrum preview
    time: str                          # HH:MM:SS UTC
    probability: float
    alert_level: str
    # Null when typing was off or nothing in-distribution was found to classify.
    burst_type: str | None = None
    type_confidence: float | None = None
    regions: list[TypedRegion] = []


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
    # Type of the most confident typed detection, and how the others voted.
    dominant_type: str | None = None
    type_counts: dict[str, int] = {}
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
    raw: bool = False                  # True = raw model output (no corroboration)
    stations: list[str]                # stations actually scored
    total_files: int                   # segments scored
    burst_count: int                   # files classified Burst
    event_count: int                   # predicted (clustered) events
    events: list[PredictedEvent] = []
    official_events: list[OfficialBurstCompare] = []
    official_count: int = 0
    matched_count: int = 0             # predicted events matching the official list
    model_id: str = ""                 # binary classifier that scored these rows
    model_name: str = ""
    classify_types: bool = False
    type_model_id: str | None = None
    type_counts: dict[str, int] = {}   # burst files per type, e.g. {"Type III": 4}


class BurstPredictionJob(BaseModel):
    job_id: str
    status: str                        # "running" | "done" | "error"
    scanned: int = 0
    total: int = 0
    date: str
    stations: list[str] = []
    model_id: str = ""
    classify_types: bool = False
    error: str | None = None
    result: BurstPredictionResult | None = None


# ── Scorecard (stored detections vs official list, trailing window) ──────────


class ScorecardDay(BaseModel):
    date: str
    has_data: bool = False             # scanner produced scored files this day
    pending: bool = False              # official list likely not published yet
    scored_files: int = 0
    burst_files: int = 0               # files classified Burst above alert minimum
    official_count: int = 0
    predicted_count: int = 0           # corroborated predicted events
    matched_official: int = 0          # official events the model matched
    matched_predicted: int = 0         # predicted events matching an official burst


class BurstScorecardResponse(BaseModel):
    days: int
    days_with_data: int = 0            # totals below cover only these days
    official_total: int = 0
    predicted_total: int = 0
    matched_official: int = 0
    matched_predicted: int = 0
    recall: float | None = None        # matched_official / official_total
    precision: float | None = None     # matched_predicted / predicted_total
    daily: list[ScorecardDay] = []


# ── Official burst list over a date range (timeline overlay) ─────────────────


class OfficialBurstItem(BaseModel):
    start_time: datetime               # UTC
    end_time: datetime
    burst_type: str                    # e.g. "III", "II", "CTM"
    stations: list[str] = []


class OfficialBurstRangeResponse(BaseModel):
    start: str                         # YYYY-MM-DD (inclusive)
    end: str
    source: str = "e-callisto"
    events: list[OfficialBurstItem] = []


# ── Offline catch-up (backfill) ──────────────────────────────────────────────


class BackfillDayCoverage(BaseModel):
    """How much of one UTC day's e-CALLISTO archive has been scored."""
    day: str                       # YYYY-MM-DD
    # "unknown" (never inspected) | pending | running | partial | done | error
    state: str
    archive_files: int = 0         # segments the archive published that day
    covered_files: int = 0         # segments with a detection row (any model)
    events: int = 0                # radio_burst events standing for the day
    model_id: str = ""
    error: str | None = None


class BackfillJob(BaseModel):
    """Progress of a catch-up run. ``day_files_*`` track the day in flight;
    ``files_*`` are cumulative for the run."""
    job_id: str
    status: Literal["running", "done", "error", "cancelled"]
    trigger: Literal["auto", "manual"]
    start_day: str
    end_day: str
    force: bool
    model_id: str
    model_name: str
    days_total: int
    days_done: int
    current_day: str | None = None
    day_files_total: int = 0
    day_files_done: int = 0
    files_scored: int = 0
    files_failed: int = 0
    events_written: int = 0
    started_at: str
    finished_at: str | None = None
    error: str | None = None
    message: str = ""


class BackfillStatusResponse(BaseModel):
    enabled: bool
    running: bool
    # How far back the automatic catch-up reaches, and the recent window it
    # deliberately leaves to the live scanner (so "today" reads as partial).
    auto_window_days: int
    live_window_hours: int
    job: BackfillJob | None = None
    coverage: list[BackfillDayCoverage] = []


class BackfillRequest(BaseModel):
    """Manual catch-up over a date range; both bounds inclusive, UTC.

    Omitting the dates runs the automatic window. ``force`` re-scores days that
    are already covered (used after switching models), which is otherwise skipped:
    a day scored by any model counts as covered.
    """
    start: str | None = None
    end: str | None = None
    force: bool = False
