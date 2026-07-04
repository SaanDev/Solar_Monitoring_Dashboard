from datetime import datetime
from typing import Literal

from pydantic import BaseModel

Severity = Literal["info", "watch", "warning", "critical"]


class NotificationSettingsPayload(BaseModel):
    """User-editable delivery preferences (PUT body)."""

    telegram_enabled: bool = False
    telegram_chat_id: str = ""
    webhook_enabled: bool = False
    webhook_url: str = ""
    min_severity: Severity = "warning"
    event_types: list[str] = []  # empty = all event types


class NotificationSettingsResponse(NotificationSettingsPayload):
    # Whether TELEGRAM_BOT_TOKEN is set server-side (the token itself is never
    # returned) — lets the UI explain why Telegram can't be enabled yet.
    telegram_token_configured: bool = False
    updated_at: datetime | None = None


class ChannelResult(BaseModel):
    ok: bool
    error: str | None = None


class NotificationTestResponse(BaseModel):
    telegram: ChannelResult | None = None  # None = channel not enabled
    webhook: ChannelResult | None = None
