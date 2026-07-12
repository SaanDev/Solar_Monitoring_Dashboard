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


# ── Type II shock analysis (Path A) ──────────────────────────────────────────


class RenderGeometry(BaseModel):
    """Plotted-area geometry of the shock spectrogram so the browser lasso can map
    screen pixels → data coordinates."""
    img_w: float
    img_h: float
    axes_px: list[float]  # [x0, y0, x1, y1] in PNG pixels, top-left origin
    t0: float
    t1: float
    freq_top: float
    freq_bottom: float


class ShockPoint(BaseModel):
    time_s: float
    freq_mhz: float


class MaxIntensityResult(BaseModel):
    """Maximum-intensity frequency per time column of the isolated burst."""
    time_channels: list[float]
    time_seconds: list[float]
    freqs: list[float]
    auto_outlier_cleaned: bool = False
    auto_removed_count: int = 0


class PowerLawFit(BaseModel):
    """Fitted f(t) = a·t^(-b) with covariance-derived standard errors."""
    a: float
    b: float
    std_errs: list[float | None] = [None, None]
    r2: float | None = None
    rmse: float | None = None
    point_count: int = 0


class ShockSummary(BaseModel):
    """Newkirk shock parameters; mirrors the desktop analyzer's summary fields."""
    avg_freq_mhz: float | None = None
    avg_freq_err_mhz: float | None = None
    avg_drift_mhz_s: float | None = None
    avg_drift_err_mhz_s: float | None = None
    start_freq_mhz: float | None = None
    start_freq_err_mhz: float | None = None
    initial_shock_speed_km_s: float | None = None
    initial_shock_speed_err_km_s: float | None = None
    initial_shock_height_rs: float | None = None
    initial_shock_height_err_rs: float | None = None
    avg_shock_speed_km_s: float | None = None
    avg_shock_speed_err_km_s: float | None = None
    avg_shock_height_rs: float | None = None
    avg_shock_height_err_rs: float | None = None
    fold: int = 1
    fundamental: bool = True
    harmonic: bool = False
    harmonic_number: int = 1
    observed_avg_freq_mhz: float | None = None
    observed_avg_drift_mhz_s: float | None = None
    observed_start_freq_mhz: float | None = None


class ShockCurves(BaseModel):
    shock_freq_mhz: list[float] = []
    shock_speed_km_s: list[float] = []
    shock_height_rs: list[float] = []


class FitLine(BaseModel):
    time_s: list[float] = []
    freq_mhz: list[float] = []


class ShockFitResult(BaseModel):
    fit: PowerLawFit
    shock_summary: ShockSummary
    curves: ShockCurves
    fit_line: FitLine


class ShockSession(BaseModel):
    """The kept maximum-intensity points + fit/summary restored from a project."""
    time_seconds: list[float] = []
    freqs: list[float] = []
    fundamental: bool = True
    harmonic: bool = False
    fold: int = 1
    fit: PowerLawFit | None = None
    shock_summary: ShockSummary | None = None


class MaxIntensityRequest(BaseModel):
    """Burst-isolation request: render params + polygon in data coordinates."""
    id: str
    method: str = "median"
    intensity_unit: str = "db"
    rfi_enabled: bool = False
    rfi_low: float = 1.0
    rfi_high: float = 99.0
    polygon: list[ShockPoint] = []
    auto_clean: bool = True


class ShockFitRequest(BaseModel):
    """Fit request: the kept points (after outlier removal) + model options."""
    id: str
    points: list[ShockPoint]
    fold: int = 1
    harmonic: bool = False
    time_channels: list[float] | None = None


class ProjectOpenResponse(BaseModel):
    session: AnalyzerSession
    settings: ProjectSettings
    shock: ShockSession | None = None
