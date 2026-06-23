import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.cache import close_cache
from app.api.routes_status import router as status_router
from app.api.routes_summary import router as summary_router
from app.api.routes_goes import router as goes_router
from app.api.routes_geomagnetic import router as geomagnetic_router
from app.api.routes_solar_indices import router as solar_indices_router
from app.api.routes_solar_images import router as solar_router
from app.api.routes_radio import router as radio_router
from app.api.routes_alerts import router as alerts_router
from app.api.routes_analyzer import router as analyzer_router

logger = logging.getLogger(__name__)


def _alembic_upgrade_head() -> None:
    """Run ``alembic upgrade head`` programmatically (blocking).

    Uses a bare Config with an explicit script_location so it works regardless of
    the process's working directory; the DB URL + metadata come from the app via
    ``alembic/env.py``. Called from a worker thread because env.py uses
    ``asyncio.run`` internally, which can't nest inside the app's event loop.
    """
    from alembic.config import Config
    from alembic import command

    backend_root = Path(__file__).resolve().parent.parent
    cfg = Config()
    cfg.set_main_option("script_location", str(backend_root / "alembic"))
    command.upgrade(cfg, "head")


async def _apply_migrations() -> None:
    """Bring the database schema up to head on startup. Never raises: a failure is
    logged so the rest of the app still serves (the DB-backed features will then
    surface their own errors)."""
    try:
        await asyncio.to_thread(_alembic_upgrade_head)
        logger.info("database schema is up to date (alembic upgrade head)")
    except Exception as exc:  # noqa: BLE001 - startup must not crash on migration error
        logger.error("automatic database migration failed: %s", exc)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings.ensure_dirs()
    if settings.auto_migrate:
        await _apply_migrations()
    # Load the burst classifier in a thread so startup isn't blocked on the
    # forward-pass warm-up. A missing/undownloadable checkpoint is non-fatal:
    # the scan will log a warning and skip scoring rather than crashing.
    if settings.radio_burst_enabled:
        import asyncio as _asyncio
        from app.ml.inference import warm_up as _ml_warm_up
        _asyncio.create_task(_asyncio.to_thread(_ml_warm_up))
    if settings.enable_scheduler:
        # Import here so the app (and tests) load without a scheduler/DB present.
        from app.scheduler import run_initial_ingest, shutdown_scheduler, start_scheduler

        start_scheduler()
        # Warm the DB in the background so startup isn't blocked on the network.
        asyncio.create_task(run_initial_ingest())
    try:
        yield
    finally:
        if settings.enable_scheduler:
            shutdown_scheduler()
        await close_cache()


app = FastAPI(
    title="Space Weather Dashboard API",
    version=settings.version,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(status_router)
app.include_router(summary_router)
app.include_router(goes_router)
app.include_router(geomagnetic_router)
app.include_router(solar_indices_router)
app.include_router(solar_router)
app.include_router(radio_router)
app.include_router(alerts_router)
app.include_router(analyzer_router)
