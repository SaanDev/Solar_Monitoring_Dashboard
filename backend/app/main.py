from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.api.routes_status import router as status_router
from app.api.routes_summary import router as summary_router
from app.api.routes_goes import router as goes_router
from app.api.routes_geomagnetic import router as geomagnetic_router
from app.api.routes_solar_images import router as solar_router
from app.api.routes_radio import router as radio_router
from app.api.routes_alerts import router as alerts_router

@asynccontextmanager
async def lifespan(app: FastAPI):
    settings.ensure_dirs()
    yield


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
app.include_router(solar_router)
app.include_router(radio_router)
app.include_router(alerts_router)
