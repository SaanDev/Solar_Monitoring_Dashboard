from datetime import datetime
from pydantic import BaseModel


class ActivityHistogramSeries(BaseModel):
    """One parameter's per-bin counts, split across ordered severity categories.

    ``counts[i]`` aligns to the shared ``bin_starts`` (see the response) and each
    inner list aligns to ``categories`` (low → high severity).
    """
    key: str
    label: str
    categories: list[str] = []
    counts: list[list[int]] = []
    total: int = 0


class ActivityHistogramResponse(BaseModel):
    """Per-parameter activity histograms over a shared, time-aligned set of bins
    (for correlating flares / radio bursts / CMEs / geomagnetic storms)."""
    start: datetime
    end: datetime
    interval_days: int
    bin_starts: list[datetime] = []
    series: list[ActivityHistogramSeries] = []


class AlertResponse(BaseModel):
    id: str
    type: str
    severity: str
    message: str
    timestamp: datetime
    source: str
    related_event_ids: list[str] = []


class EventResponse(BaseModel):
    id: str
    type: str
    severity: str | None = None
    start_time: datetime
    end_time: datetime | None = None
    peak_time: datetime | None = None
    peak_value: float | None = None
    description: str
    # Observing stations for station-based events (radio bursts); empty otherwise.
    stations: list[str] = []
    # Radio bursts only: "Type II" | "Type III" | "Other" from the burst-type
    # classifier. Null when typing was off or nothing was classifiable.
    burst_type: str | None = None
    related_event_ids: list[str] = []
    source_url: str | None = None
    # Id of the causal storyline this event belongs to (None if it stands alone).
    chain_id: str | None = None


class EventChain(BaseModel):
    """A causal storyline: physically-associated events (flare -> CME -> radio
    burst -> proton event -> geomagnetic storm) assembled into one sequence."""
    chain_id: str
    start_time: datetime
    end_time: datetime | None = None
    summary: str                       # deterministic one-line narrative
    peak_severity: str                 # highest member alert level (info..critical)
    event_ids: list[str] = []          # member ids in causal order
    roles: dict[str, str] = {}         # event id -> causal role (flare, cme, sep, ...)
    events: list[EventResponse] = []   # member events in causal order
