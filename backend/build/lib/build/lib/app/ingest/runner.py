"""Run ingestion for one or all sources, recording health in source_status."""
import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.ingest.sources import SOURCES, IngestSource
from app.repositories.status_repo import record_error, record_success
from app.repositories.timeseries_repo import upsert_points

logger = logging.getLogger(__name__)


async def run_ingest(db: AsyncSession, src: IngestSource) -> int:
    """Fetch + upsert one source. Failures are recorded, not raised."""
    try:
        records = await src.collect()
        count = await upsert_points(db, src.model, records, src.source_tag)
        await record_success(db, src.name)
        logger.info("ingested %d rows for %s", count, src.name)
        return count
    except Exception as exc:
        await db.rollback()
        await record_error(db, src.name, str(exc))
        logger.warning("ingest failed for %s: %s", src.name, exc)
        return 0


async def run_all(db: AsyncSession) -> None:
    for src in SOURCES:
        await run_ingest(db, src)
