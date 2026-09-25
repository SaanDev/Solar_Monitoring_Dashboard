from datetime import datetime
from pydantic import BaseModel


class KpPoint(BaseModel):
    time: datetime
    kp: float


class DstPoint(BaseModel):
    time: datetime
    dst: float


class KpLatest(BaseModel):
    time: datetime | None = None
    kp: float | None = None
    g_scale: str | None = None


class DstLatest(BaseModel):
    time: datetime | None = None
    dst: float | None = None
    storm_level: str | None = None
