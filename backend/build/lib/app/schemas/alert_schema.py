from datetime import datetime
from pydantic import BaseModel


class AlertResponse(BaseModel):
    id: str
    type: str
    severity: str
    message: str
    timestamp: datetime
    source: str


class EventResponse(BaseModel):
    id: str
    type: str
    severity: str | None = None
    start_time: datetime
    end_time: datetime | None = None
    peak_time: datetime | None = None
    peak_value: float | None = None
    description: str
    related_event_ids: list[str] = []
    source_url: str | None = None
