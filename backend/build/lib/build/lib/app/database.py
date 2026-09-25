from datetime import datetime, timezone

from sqlalchemy import DateTime, event
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.types import TypeDecorator

from app.config import settings

engine = create_async_engine(settings.database_url, echo=False)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


if engine.dialect.name == "sqlite":
    # The desktop app runs on a SQLite file instead of Postgres (app/desktop.py).
    # The scheduler, the burst backfill and API requests all write concurrently,
    # so: WAL lets readers proceed while a write is in flight, and busy_timeout
    # makes a second writer wait for the lock instead of failing immediately
    # with "database is locked". synchronous=NORMAL is the standard WAL pairing
    # (durable against crashes; only the last commit is at risk on power loss).
    @event.listens_for(engine.sync_engine, "connect")
    def _sqlite_pragmas(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=30000")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.close()


class UTCDateTime(TypeDecorator):
    """``DateTime(timezone=True)`` that always hands back UTC-aware datetimes.

    Postgres already does (timestamptz), so there this is a no-op. SQLite has no
    timezone type: it stores the wall-clock text and returns *naive* datetimes,
    which then blow up on comparison with the aware values the rest of the app
    uses. So on the way in, aware values are normalised to UTC before SQLite
    drops the offset, and on the way out naive values are re-tagged as UTC.
    """

    impl = DateTime
    cache_ok = True

    def __init__(self) -> None:
        super().__init__(timezone=True)

    def process_bind_param(self, value: datetime | None, dialect) -> datetime | None:
        if value is not None and value.tzinfo is not None and dialect.name == "sqlite":
            return value.astimezone(timezone.utc)
        return value

    def process_result_value(self, value: datetime | None, dialect) -> datetime | None:
        if value is not None and value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        yield session
