import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.config import settings
from app.cache import close_cache
from app.api.routes_status import router as status_router
from app.api.routes_summary import router as summary_router
from app.api.routes_goes import router as goes_router
from app.api.routes_geomagnetic import router as geomagnetic_router
from app.api.routes_solar_indices import router as solar_indices_router
from app.api.routes_solar_wind import router as solar_wind_router
from app.api.routes_forecast import router as forecast_router
from app.api.routes_notifications import router as notifications_router
from app.api.routes_solar_images import router as solar_router
from app.api.routes_radio import router as radio_router
from app.api.routes_alerts import router as alerts_router
from app.api.routes_analyzer import router as analyzer_router
from app.api.routes_data_analysis import router as data_analysis_router

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


async def _restore_model_selection() -> None:
    """Re-apply the burst model chosen on the Settings page.

    The choice is stored in the database so it outlives the process, but the
    registry keeps it in memory (so model lookups stay synchronous), which means
    it has to be read back before the first scan or request. Never fatal: an
    unreachable database just leaves the configured default in charge.
    """
    from app.database import AsyncSessionLocal
    from app.services.model_settings_service import load_saved_binary_model

    try:
        async with AsyncSessionLocal() as db:
            await load_saved_binary_model(db)
    except Exception as exc:  # noqa: BLE001 - startup must not crash on this
        logger.warning("could not restore the saved burst-model selection: %s", exc)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings.ensure_dirs()
    if settings.auto_migrate:
        await _apply_migrations()
    # Load the burst classifiers the scanner will use (the selected/configured
    # binary model, plus the burst-type model when typing is on) in a thread, so
    # startup isn't blocked on the forward-pass warm-up. A missing/undownloadable
    # checkpoint is non-fatal: the scan logs a warning and skips scoring rather
    # than crashing. The saved selection is restored first so the *right*
    # checkpoint is the one warmed.
    if settings.radio_burst_enabled:
        await _restore_model_selection()
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

class _DesktopOriginGuard:
    """Refuse state-changing requests sent from other websites (desktop only).

    The desktop backend listens on 127.0.0.1, so any page open in the user's
    browser can *send* it a POST — CORS only stops that page reading the reply.
    Browsers always attach ``Origin`` to cross-origin writes, so rejecting a
    foreign one blocks that while leaving local non-browser clients (no
    ``Origin`` header) alone.
    """

    _SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})

    def __init__(self, app, allowed_origins: list[str]) -> None:
        self.app = app
        self.allowed = frozenset(allowed_origins)

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] == "http" and scope["method"] not in self._SAFE_METHODS:
            origin = next(
                (v.decode("latin-1") for k, v in scope["headers"] if k == b"origin"), None
            )
            if origin is not None and origin not in self.allowed:
                response = JSONResponse({"detail": "cross-origin request refused"}, status_code=403)
                await response(scope, receive, send)
                return
        await self.app(scope, receive, send)


class _FrontendFiles(StaticFiles):
    """The Next.js static export, served at "/" by the desktop backend.

    Unknown ``/api/...`` paths fall through the routers to this mount; they must
    stay JSON 404s (the frontend reads ``detail``) rather than get the HTML 404
    page, so they are refused here before the file lookup.
    """

    async def get_response(self, path: str, scope):
        # `path` has been through os.path.normpath, so on Windows it arrives as
        # "api\\x" — compare segments, not a "api/" prefix.
        if Path(path).parts[:1] == ("api",):
            raise StarletteHTTPException(status_code=404)
        return await super().get_response(path, scope)


app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
if settings.desktop_mode:
    app.add_middleware(_DesktopOriginGuard, allowed_origins=settings.cors_origins_list)

app.include_router(status_router)
app.include_router(summary_router)
app.include_router(goes_router)
app.include_router(geomagnetic_router)
app.include_router(solar_indices_router)
app.include_router(solar_wind_router)
app.include_router(forecast_router)
app.include_router(notifications_router)
app.include_router(solar_router)
app.include_router(radio_router)
app.include_router(alerts_router)
app.include_router(analyzer_router)
app.include_router(data_analysis_router)

# Desktop app: serve the dashboard UI from the same origin as the API. Mounted
# last so every /api route above matches first.
if settings.frontend_dist_dir:
    app.mount("/", _FrontendFiles(directory=settings.frontend_dist_dir, html=True), name="frontend")
