from datetime import datetime
from pydantic import BaseModel


class SolarImageResponse(BaseModel):
    id: str
    source: str
    instrument: str
    wavelength: str
    timestamp: datetime
    thumbnail_url: str
    full_url: str


class LascoMovieResponse(BaseModel):
    camera: str
    url: str
    timestamp: datetime
