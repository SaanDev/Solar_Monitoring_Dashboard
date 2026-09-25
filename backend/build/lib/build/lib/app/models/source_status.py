"""Per-source ingestion health, surfaced by ``/api/sources/status``."""
from datetime import datetime, timezone

from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base, UTCDateTime


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class SourceStatus(Base):
    __tablename__ = "source_status"

    # Matches the human-readable names used by the status endpoint.
    name: Mapped[str] = mapped_column(String(64), primary_key=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="unknown")
    last_success_at: Mapped[datetime | None] = mapped_column(
        UTCDateTime(), nullable=True
    )
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), default=_utcnow, onupdate=_utcnow, nullable=False
    )
