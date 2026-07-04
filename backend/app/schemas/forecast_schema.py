from datetime import datetime

from pydantic import BaseModel

# ── Predicted Kp (Newell coupling from L1 solar wind) ────────────────────────


class KpForecastPoint(BaseModel):
    time: datetime
    kp: float | None = None          # trailing-hour smoothed predicted Kp


class KpForecastLatest(BaseModel):
    time: datetime | None = None
    kp: float | None = None          # smoothed predicted Kp (next ~1-3 h)
    coupling: float | None = None    # Newell d(phi)/dt, smoothed
    g_scale: str | None = None       # NOAA G level this Kp maps to (None = no storm)


class KpForecastResponse(BaseModel):
    range: str
    source: str = "noaa-swpc"
    latest: KpForecastLatest = KpForecastLatest()
    data: list[KpForecastPoint] = []


# ── CMEs (NASA DONKI catalog + WSA-ENLIL arrival) ────────────────────────────


class CmeItem(BaseModel):
    activity_id: str
    start_time: datetime
    source_location: str | None = None
    active_region: int | None = None
    latitude: float | None = None
    longitude: float | None = None
    half_angle: float | None = None   # cone half-width, degrees
    speed: float | None = None        # radial speed at 21.5 Rs, km/s
    cme_type: str | None = None       # DONKI class: S/C/O/R/ER
    time21_5: datetime | None = None
    is_earth_directed: bool = False
    predicted_arrival_time: datetime | None = None
    predicted_kp: float | None = None
    note: str = ""
    catalog_link: str | None = None


class CmeListResponse(BaseModel):
    days: int
    source: str = "nasa-donki"
    cmes: list[CmeItem] = []


# ── NOAA 3-day R/S/G outlook ─────────────────────────────────────────────────


class NoaaScaleDay(BaseModel):
    date: str | None = None
    # Radio blackouts (flares): observed level or forecast probabilities (%).
    r_scale: str | None = None
    r_text: str | None = None
    r_minor_prob: int | None = None   # P(R1-R2)
    r_major_prob: int | None = None   # P(R3+)
    # Solar radiation storms (protons).
    s_scale: str | None = None
    s_text: str | None = None
    s_prob: int | None = None         # P(S1+)
    # Geomagnetic storms.
    g_scale: str | None = None
    g_text: str | None = None


class NoaaScalesResponse(BaseModel):
    issued: datetime | None = None
    source: str = "noaa-swpc"
    observed: NoaaScaleDay | None = None   # yesterday's reached maxima
    current: NoaaScaleDay | None = None    # today so far
    forecast: list[NoaaScaleDay] = []      # next 3 days


# ── OVATION aurora forecast ──────────────────────────────────────────────────


class AuroraForecast(BaseModel):
    observation_time: datetime | None = None
    forecast_time: datetime | None = None
    power_north_gw: float | None = None
    power_south_gw: float | None = None
    north_image_url: str
    south_image_url: str
    source: str = "noaa-swpc-ovation"
