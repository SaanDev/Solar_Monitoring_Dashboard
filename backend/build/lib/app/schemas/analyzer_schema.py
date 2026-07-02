from datetime import datetime

from pydantic import BaseModel


class AnalyzerSession(BaseModel):
    """Metadata for an uploaded / archive-imported FITS held server-side by id."""
    id: str
    station: str
    filename: str
    n_freq: int
    n_time: int
    freq_min_mhz: float
    freq_max_mhz: float
    start_time: datetime | None = None
    end_time: datetime | None = None
    duration_s: float = 0.0


class AnalyzerStats(BaseModel):
    """Processed-data range for driving the display (vmin/vmax) sliders."""
    data_min: float
    data_max: float
    vmin: float
    vmax: float


class ProjectSettings(BaseModel):
    """Restorable render settings carried in a .efaproj project."""
    method: str = "median"
    intensity_unit: str = "db"
    time_unit: str = "seconds"
    cmap: str = "magma"
    vmin: float | None = None
    vmax: float | None = None
    rfi_enabled: bool = False
    rfi_low: float = 1.0
    rfi_high: float = 99.0


class ProjectOpenResponse(BaseModel):
    session: AnalyzerSession
    settings: ProjectSettings
