from datetime import datetime
from pydantic import BaseModel


class SummaryLatest(BaseModel):
    timestamp: datetime
    goes_xray_class: str | None = None
    goes_xray_flux: float | None = None
    proton_flux_10mev: float | None = None
    kp_index: float | None = None
    dst_index: float | None = None
    solar_wind_speed: float | None = None
    active_alerts: int = 0
