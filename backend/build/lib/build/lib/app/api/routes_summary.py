from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas.summary_schema import SummaryLatest
from app.services.goes_xrs_service import get_goes_xrs_latest
from app.services.goes_proton_service import get_goes_proton_latest
from app.services.kp_service import get_kp_latest
from app.services.dst_service import get_dst_latest
from app.services.event_service import get_latest_alerts
from app.services.solar_wind_service import get_solar_wind_latest
from app.services.sunspot_service import get_sunspot_latest

router = APIRouter(prefix="/api/summary", tags=["summary"])


@router.get("/latest", response_model=SummaryLatest)
async def get_summary_latest(db: AsyncSession = Depends(get_db)) -> SummaryLatest:
    # Each source is independent: one failing must not blank the whole summary.
    try:
        xrs = await get_goes_xrs_latest(db)
        xray_class = xrs.flare_class
        xray_flux = xrs.long_channel
    except Exception:
        xray_class = None
        xray_flux = None

    try:
        proton = await get_goes_proton_latest(db)
        proton_flux = proton.flux_gt10
        proton_event = proton.event_in_progress
    except Exception:
        proton_flux = None
        proton_event = False

    try:
        kp = (await get_kp_latest(db)).kp
    except Exception:
        kp = None

    try:
        dst = (await get_dst_latest(db)).dst
    except Exception:
        dst = None

    try:
        sw = await get_solar_wind_latest()
        wind_speed, imf_bz, imf_bt = sw.speed, sw.bz, sw.bt
    except Exception:
        wind_speed = imf_bz = imf_bt = None

    try:
        sunspot = (await get_sunspot_latest()).number
    except Exception:
        sunspot = None

    try:
        active_alerts = len(await get_latest_alerts(db))
    except Exception:
        # Fall back to the proton flag so a stale/empty events table doesn't
        # under-report an in-progress radiation storm.
        active_alerts = 1 if proton_event else 0

    return SummaryLatest(
        timestamp=datetime.now(timezone.utc),
        goes_xray_class=xray_class,
        goes_xray_flux=xray_flux,
        proton_flux_10mev=proton_flux,
        kp_index=kp,
        dst_index=dst,
        solar_wind_speed=wind_speed,
        sunspot_number=sunspot,
        imf_bz=imf_bz,
        imf_bt=imf_bt,
        active_alerts=active_alerts,
    )
