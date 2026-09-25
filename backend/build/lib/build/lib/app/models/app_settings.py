"""Runtime-editable application settings (single row, id=1).

``app/config.py`` holds the *environment* defaults a deployment ships with.
This table holds the choices made from the dashboard's Settings page, which
have to outlive the process and apply to the background scheduler just as much
as to API requests — an env var can do neither without a restart and a file edit.

One field today: which binary burst classifier the automatic radio-burst scan
runs. Empty means "follow ``RADIO_BURST_BINARY_MODEL``", so a database whose
row was never written behaves exactly as it did before this table existed.
"""
from datetime import datetime, timezone

from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base, UTCDateTime


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class AppSettings(Base):
    __tablename__ = "app_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)  # always 1

    # Binary burst classifier for the automatic scan; "" = use the configured
    # default. Ids come from app/ml/registry.py ("ccm-1.0.0" | "ccm-1.1.0").
    radio_burst_binary_model: Mapped[str] = mapped_column(
        String(64), nullable=False, default=""
    )

    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), default=_utcnow, onupdate=_utcnow, nullable=False
    )
