"""APScheduler wiring: periodic ingestion jobs, one per source.

Each job opens its own DB session (jobs run outside any request). The scheduler
is started/stopped from the app lifespan; an initial run warms the DB on startup.
"""
import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.database import AsyncSessionLocal
from app.ingest.runner import run_all, run_ingest
from app.ingest.sources import SOURCES, IngestSource

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler(timezone="UTC")


async def _job(src: IngestSource) -> None:
    async with AsyncSessionLocal() as db:
        await run_ingest(db, src)


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
    scheduler.start()
    logger.info("scheduler started with %d jobs", len(SOURCES))


async def run_initial_ingest() -> None:
    """One-shot ingest on startup so the DB is warm before the first interval."""
    async with AsyncSessionLocal() as db:
        await run_all(db)


def shutdown_scheduler() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)
