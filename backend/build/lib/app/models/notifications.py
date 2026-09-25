"""Alert-delivery ORM models.

``notification_settings`` is a single-row table (id=1) holding the user's
delivery preferences, edited from the dashboard's Settings page. Channel
*secrets* (the Telegram bot token) intentionally live in the environment, not
here — the DB stores only routing (chat id / webhook URL) and filtering.

``sent_notifications`` is the dedup ledger: one row per event already
delivered, keyed by the event id (``type:start_time``), remembering the
severity it was sent at so an escalation (e.g. M-flare grows into X) can
re-notify while re-runs of the same event stay silent.
"""
from datetime import datetime, timezone

from sqlalchemy import Boolean, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base, UTCDateTime


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class NotificationSettings(Base):
    __tablename__ = "notification_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)  # always 1

    telegram_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    telegram_chat_id: Mapped[str] = mapped_column(String(64), nullable=False, default="")

    webhook_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    webhook_url: Mapped[str] = mapped_column(Text, nullable=False, default="")

    # Lowest alert level that gets delivered: "info" | "watch" | "warning" | "critical".
    min_severity: Mapped[str] = mapped_column(String(16), nullable=False, default="warning")
    # Comma-separated event types to deliver; empty = all types.
    event_types: Mapped[str] = mapped_column(Text, nullable=False, default="")

    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), default=_utcnow, onupdate=_utcnow, nullable=False
    )


class SentNotification(Base):
    __tablename__ = "sent_notifications"

    event_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    sent_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), default=_utcnow, nullable=False
    )
