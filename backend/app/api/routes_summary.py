from datetime import datetime, timezone

from fastapi import APIRouter

from app.schemas.summary_schema import SummaryLatest
from app.services.goes_xrs_service import get_goes_xrs_latest
from app.services.goes_proton_service import get_goes_proton_latest
from app.services.kp_service import get_kp_latest
from app.services.dst_service import get_dst_latest

router = APIRouter(prefix="/api/summary", tags=["summary"])


@router.get("/latest", response_model=SummaryLatest)
async def get_summary_latest() -> SummaryLatest:
    # GOES XRS + proton are live; remaining fields stay mock until their collectors are wired.
    try:
        xrs = await get_goes_xrs_latest()
        xray_class = xrs.flare_class
        xray_flux = xrs.long_channel
    except Exception:
        xray_class = None
        xray_flux = None

    try:
        proton = await get_goes_proton_latest()
        proton_flux = proton.flux_gt10
        proton_event = proton.event_in_progress
    except Exception:
        proton_flux = None
        proton_event = False

    try:
        kp = (await get_kp_latest()).kp
    except Exception:
        kp = None

    try:
        dst = (await get_dst_latest()).dst
    except Exception:
        dst = None

    return SummaryLatest(
        timestamp=datetime.now(timezone.utc),
        goes_xray_class=xray_class,
        goes_xray_flux=xray_flux,
        proton_flux_10mev=proton_flux,
        kp_index=kp,
        dst_index=dst,
        solar_wind_speed=420.0,
        active_alerts=1 if proton_event else 0,
    )
