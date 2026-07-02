"""Schemas for the SDO/AIA Data Analysis feature.

A *session* holds one or more solar FITS frames stored server-side under
``settings.analysis_dir/<id>/`` (uploaded, Fido-fetched, or pulled from the JSOC
synoptic archive). Single-image plots/crops render synchronously; multi-frame work
(fetch sequences, running difference, movies) runs as a background *job* whose
progress is polled via ``/api/analysis/jobs/{job_id}``.
"""
from datetime import datetime

from pydantic import BaseModel


class FrameMeta(BaseModel):
    index: int
    time: datetime | None = None
    filename: str


class AnalysisSession(BaseModel):
    """Metadata for a solar-image session held server-side by id."""
    id: str
    source: str                       # "upload" | "fetch" | "archive"
    observatory: str = ""             # e.g. "SDO"
    instrument: str = ""              # e.g. "AIA"
    detector: str = ""                # e.g. "AIA"
    measurement: str = ""             # human label, e.g. "171 Å" / "magnetogram"
    wavelength_angstrom: float | None = None
    reference_time: datetime | None = None
    width: int = 0
    height: int = 0
    n_frames: int = 1
    frames: list[FrameMeta] = []


class WavelengthOption(BaseModel):
    code: str                         # AIA wavelength code, e.g. "171"
    label: str                        # "AIA 171 Å"


class AnalysisOptions(BaseModel):
    wavelengths: list[WavelengthOption]
    colormaps: list[str]
    scales: list[str]
    difference_types: list[str]
    movie_formats: list[str]
    max_frames: int


class FetchRequest(BaseModel):
    """Fetch a single AIA frame nearest a UTC time via SunPy Fido (VSO)."""
    wavelength: str                   # AIA channel code, e.g. "171"
    time: datetime                    # UTC observation time
    prep: bool = False                # aiapy level-1.5 prep (slow; downloads tables)


class ArchiveRequest(BaseModel):
    """Pull a 1024px synoptic frame from the existing JSOC archive pipeline."""
    date: str                         # YYYY-MM-DD (UTC)
    time: str = "12:00"               # HH:MM (UTC)
    wavelength: str                   # AIA channel code, e.g. "171"


class SequenceRequest(BaseModel):
    """Build a multi-frame session from the JSOC synoptic archive (for difference
    images and movies)."""
    date: str                         # YYYY-MM-DD (UTC)
    start_time: str = "00:00"         # HH:MM (UTC) of the first frame
    step_min: int = 5                 # minutes between frames
    n_frames: int = 10                # number of frames
    wavelength: str = "171"           # AIA channel code


class MovieRequest(BaseModel):
    """Build a time-lapse movie from a multi-frame session."""
    session: str
    fmt: str = "mp4"                  # mp4 | gif
    fps: int = 8
    mode: str = "plot"               # plot | difference (running)
    cmap: str = "auto"
    scale: str = "sqrt"
    clip_low: float = 1.0
    clip_high: float = 99.5
    crop: bool = False
    bl_x: float = 0.0
    bl_y: float = 0.0
    tr_x: float = 0.0
    tr_y: float = 0.0


class JobStatusResponse(BaseModel):
    """Uniform progress record for any background analysis job."""
    job_id: str
    state: str                        # pending | running | done | error
    progress: float = 0.0
    message: str = ""
    error: str | None = None
    # A fetch job yields a session; render/difference/composite/movie jobs yield a
    # downloadable artifact at /api/analysis/result/{job_id}.
    session: AnalysisSession | None = None
    result_url: str | None = None
    meta: dict | None = None
