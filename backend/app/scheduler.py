"""APScheduler wiring: periodic ingestion jobs, one per source.

Each job opens its own DB session (jobs run outside any request). The scheduler
is started/stopped from the app lifespan; an initial run warms the DB on startup.
"""
import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.database import AsyncSessionLocal
from app.ingest.runner import run_all, run_ingest
from app.ingest.sources import SOURCES, IngestSource
from app.services.event_service import detect_and_store

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
    scheduler.start()
    logger.info("scheduler started with %d ingest jobs + event detection", len(SOURCES))


async def run_initial_ingest() -> None:
    """One-shot ingest on startup so the DB is warm before the first interval,
    then a detection pass so events exist immediately."""
    async with AsyncSessionLocal() as db:
        await run_all(db)
        await detect_and_store(db)


def shutdown_scheduler() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)
