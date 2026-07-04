"""APScheduler wiring: periodic ingestion jobs, one per source.

Each job opens its own DB session (jobs run outside any request). The scheduler
is started/stopped from the app lifespan; an initial run warms the DB on startup.
"""
import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.config import settings
from app.database import AsyncSessionLocal
from app.ingest.runner import run_all, run_ingest
from app.ingest.sources import SOURCES, IngestSource
from app.services.cme_service import collect_and_store as collect_cmes
from app.services.event_service import detect_and_store
from app.services.forecast_service import detect_and_store_predicted_storms
from app.services.notification_service import dispatch_pending
from app.services.radio_burst_service import scan_and_detect_radio_bursts

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler(timezone="UTC")

# How often to re-derive events from the freshly ingested time-series.
_DETECTION_INTERVAL_SECONDS = 600


async def _job(src: IngestSource) -> None:
    async with AsyncSessionLocal() as db:
        await run_ingest(db, src)


async def _detection_job() -> None:
    async with AsyncSessionLocal() as db:
        await detect_and_store(db)


async def _radio_burst_job() -> None:
    async with AsyncSessionLocal() as db:
        await scan_and_detect_radio_bursts(db)


async def _cme_job() -> None:
    async with AsyncSessionLocal() as db:
        await collect_cmes(db)


async def _forecast_job() -> None:
    async with AsyncSessionLocal() as db:
        await detect_and_store_predicted_storms(db)


async def _notify_job() -> None:
    async with AsyncSessionLocal() as db:
        await dispatch_pending(db)


def start_scheduler() -> None:
    for src in SOURCES:
        scheduler.add_job(
            _job,
            trigger="interval",
            seconds=src.interval_seconds,
            args=[src],
            id=src.name,
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )
    scheduler.add_job(
        _detection_job,
        trigger="interval",
        seconds=_DETECTION_INTERVAL_SECONDS,
        id="event-detection",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    if settings.radio_burst_enabled:
        scheduler.add_job(
            _radio_burst_job,
            trigger="interval",
            seconds=settings.radio_burst_scan_interval,
            id="radio-burst-scan",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )
    scheduler.add_job(
        _cme_job,
        trigger="interval",
        seconds=settings.cme_poll_seconds,
        id="cme-ingest",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        _forecast_job,
        trigger="interval",
        seconds=_DETECTION_INTERVAL_SECONDS,
        id="kp-forecast-detection",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        _notify_job,
        trigger="interval",
        seconds=settings.notify_dispatch_seconds,
        id="alert-notify",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    scheduler.start()
    logger.info(
        "scheduler started with %d ingest jobs + event detection%s",
        len(SOURCES),
        " + radio-burst scan" if settings.radio_burst_enabled else "",
    )


async def run_initial_ingest() -> None:
    """One-shot ingest on startup so the DB is warm before the first interval,
    then a detection pass so events exist immediately."""
    async with AsyncSessionLocal() as db:
        await run_all(db)
        await detect_and_store(db)
        await collect_cmes(db)
        await detect_and_store_predicted_storms(db)
        if settings.radio_burst_enabled:
            await scan_and_detect_radio_bursts(db)


def shutdown_scheduler() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)
