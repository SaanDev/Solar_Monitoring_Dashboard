"""Shared test fixtures.

Backs the app with an in-memory SQLite database (a single shared connection via
StaticPool) and overrides ``get_db`` so tests never need a real Postgres. The
repository layer is dialect-aware, so the same upsert/query code runs here.
"""
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.config import settings
from app.database import Base, get_db
import app.models  # noqa: F401  registers all tables on Base.metadata (import before `app`)
from app.main import app

# The scheduler must never start during tests (no network, no real DB).
settings.enable_scheduler = False
# Tests build the schema with create_all (SQLite); never run alembic/Postgres.
settings.auto_migrate = False


@pytest_asyncio.fixture
async def db_engine():
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def sessionmaker(db_engine):
    return async_sessionmaker(db_engine, expire_on_commit=False)


@pytest_asyncio.fixture
async def db_session(sessionmaker):
    async with sessionmaker() as session:
        yield session


@pytest_asyncio.fixture(autouse=True)
async def override_get_db(sessionmaker):
    async def _get_db():
        async with sessionmaker() as session:
            yield session

    app.dependency_overrides[get_db] = _get_db
    yield
    app.dependency_overrides.pop(get_db, None)


@pytest.fixture(autouse=True)
def fake_cache(monkeypatch):
    """Replace Redis with a per-test in-memory store so caching is deterministic
    and tests don't depend on a running Redis."""
    store: dict[str, str] = {}

    class _FakeRedis:
        async def get(self, key):
            return store.get(key)

        async def set(self, key, value, ex=None):
            store[key] = value

        async def aclose(self):
            store.clear()

    monkeypatch.setattr("app.cache.get_client", lambda: _FakeRedis())


@pytest.fixture
def trust_all_stations(monkeypatch):
    """Take station knowledge out of the multi-station burst confirmation.

    For tests about the burst *pipeline* (scanning, dedup, persistence, types,
    backfill, the predictor's plumbing) rather than about how stations are
    weighed: every station has the same clean record (a high-confidence flag is
    strong evidence, a mid one good evidence, silence mildly against), and no
    station has a known location — so each is its own site and counts as sun-up
    whatever the wall-clock time of the test run. ``test_burst_confirmation.py``
    covers the real station handling.
    """
    from app.processing.burst_confirmation import EvidenceTable, StationEvidence
    from app.processing.callisto_stations import STATION_LOCATIONS
    from app.services import station_reliability_service as reliability

    monkeypatch.setattr(
        reliability,
        "_table_from",
        lambda rows: EvidenceTable({}, default=StationEvidence(llr=(-0.5, 0.2, 2.0, 3.0))),
    )
    monkeypatch.setattr(reliability, "_cache", None)
    saved = dict(STATION_LOCATIONS)
    STATION_LOCATIONS.clear()
    yield
    STATION_LOCATIONS.update(saved)


@pytest.fixture(autouse=True)
def _fresh_reliability_cache(monkeypatch):
    """The station-reliability votes are cached in-process; start each test cold."""
    from app.services import station_reliability_service as reliability

    monkeypatch.setattr(reliability, "_cache", None)
