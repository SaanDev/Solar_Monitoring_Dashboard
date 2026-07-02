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


class SolarArchiveImage(BaseModel):
    id: str                       # catalog key, e.g. "aia171"
    source: str                   # SDO, SOHO
    instrument: str               # AIA, HMI, LASCO
    measurement: str              # 171, continuum, C2
    label: str                    # "AIA 171 Å"
    source_id: int                # Helioviewer sourceId
    supports_events: bool         # active-region overlay applies (disk images)
    time: datetime | None = None  # actual closest observation time
    image_url: str                # rendered PNG (Helioviewer, direct)
    png_download_url: str         # our proxy, attachment
    jp2_download_url: str         # raw JPEG2000, our proxy, attachment
    fits_available: bool = False  # raw FITS obtainable (AIA/HMI via JSOC)
    fts_download_url: str | None = None  # raw FITS, our proxy, attachment


class SolarArchiveResponse(BaseModel):
    date: str
    time: str
    with_events: bool
    images: list[SolarArchiveImage] = []
