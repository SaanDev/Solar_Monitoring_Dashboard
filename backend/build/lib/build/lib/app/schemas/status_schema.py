from datetime import datetime
from pydantic import BaseModel


class StatusResponse(BaseModel):
    service: str
    status: str
    timestamp: datetime
    version: str


class SourceStatus(BaseModel):
    name: str
    status: str
    last_updated: datetime | None = None
    message: str | None = None


class SourcesStatusResponse(BaseModel):
    sources: list[SourceStatus]
