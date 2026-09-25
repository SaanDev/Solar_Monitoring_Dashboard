"""Alert delivery — push qualifying alerts to Telegram / a webhook.

A scheduled dispatch pass reads the current alert view (derived events),
filters it by the user's stored preferences (minimum severity, event types,
recency), skips everything already in the ``sent_notifications`` ledger, and
pushes the rest. An event whose severity *escalated* since it was sent (e.g.
an M-flare growing into an X) is re-sent with an "escalated" marker.

Flood control: enabling a channel baselines the ledger with every currently
qualifying alert (so switching notifications on doesn't replay recent history),
and each pass sends at most ``notify_max_per_pass`` messages, oldest first —
a genuine burst of activity drains over a few passes instead of spamming.

The Telegram bot token is a server-side secret (``TELEGRAM_BOT_TOKEN`` in
.env); the DB stores only routing (chat id / webhook URL) and filters.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.notifications import NotificationSettings
from app.repositories.notification_repo import (
    get_or_create_settings,
    record_sent,
    save_settings,
    sent_severities,
)
from app.schemas.alert_schema import AlertResponse
from app.schemas.notification_schema import (
    ChannelResult,
    NotificationSettingsResponse,
    NotificationTestResponse,
)
from app.services.event_service import get_latest_alerts

logger = logging.getLogger(__name__)

SEVERITY_RANK = {"info": 0, "watch": 1, "warning": 2, "critical": 3}
_SEVERITY_ICON = {"info": "🔵", "watch": "🟡", "warning": "🟠", "critical": "🔴"}

_TIMEOUT = 10


# ── Settings ─────────────────────────────────────────────────────────────────


def _to_response(row: NotificationSettings) -> NotificationSettingsResponse:
    return NotificationSettingsResponse(
        telegram_enabled=row.telegram_enabled,
        telegram_chat_id=row.telegram_chat_id,
        webhook_enabled=row.webhook_enabled,
        webhook_url=row.webhook_url,
        min_severity=row.min_severity if row.min_severity in SEVERITY_RANK else "warning",
        event_types=[t for t in row.event_types.split(",") if t],
        telegram_token_configured=bool(settings.telegram_bot_token),
        updated_at=row.updated_at,
    )


async def get_notification_settings(db: AsyncSession) -> NotificationSettingsResponse:
    return _to_response(await get_or_create_settings(db))


async def update_notification_settings(
    db: AsyncSession, payload: dict
) -> NotificationSettingsResponse:
    """Persist preferences; when delivery goes from fully off to on, baseline
    the ledger so only events *after* enabling are pushed."""
    current = await get_or_create_settings(db)
    was_enabled = current.telegram_enabled or current.webhook_enabled

    values = dict(payload)
    values["event_types"] = ",".join(payload.get("event_types") or [])
    row = await save_settings(db, values)

    now_enabled = row.telegram_enabled or row.webhook_enabled
    if now_enabled and not was_enabled:
        alerts = await _qualifying_alerts(db, row)
        await record_sent(db, [(a.id.removeprefix("alert:"), a.severity) for a in alerts])
        logger.info("notification baseline: %d existing alerts marked sent", len(alerts))
    return _to_response(row)


# ── Dispatch ─────────────────────────────────────────────────────────────────


def _as_utc(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


async def _qualifying_alerts(
    db: AsyncSession, s: NotificationSettings
) -> list[AlertResponse]:
    """Current alerts that pass the stored filters, newest first."""
    min_rank = SEVERITY_RANK.get(s.min_severity, 2)
    wanted = {t for t in s.event_types.split(",") if t}
    cutoff = datetime.now(timezone.utc) - timedelta(hours=settings.notify_lookback_hours)
    out = []
    for a in await get_latest_alerts(db):
        if SEVERITY_RANK.get(a.severity, 0) < min_rank:
            continue
        if wanted and a.type not in wanted:
            continue
        if _as_utc(a.timestamp) < cutoff:
            continue
        out.append(a)
    return out


def format_message(a: AlertResponse, escalated: bool = False) -> str:
    icon = _SEVERITY_ICON.get(a.severity, "⚪")
    tag = " (escalated)" if escalated else ""
    when = _as_utc(a.timestamp).strftime("%Y-%m-%d %H:%M UTC")
    return f"{icon} SWDash {a.severity.upper()}{tag}\n{a.message}\n{when}"


async def _send_telegram(chat_id: str, text: str) -> ChannelResult:
    if not settings.telegram_bot_token:
        return ChannelResult(ok=False, error="TELEGRAM_BOT_TOKEN not configured")
    if not chat_id:
        return ChannelResult(ok=False, error="chat id not set")
    url = f"{settings.telegram_api_base}/bot{settings.telegram_bot_token}/sendMessage"
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            r = await client.post(url, json={"chat_id": chat_id, "text": text})
        if r.status_code != 200:
            desc = ""
            try:
                desc = r.json().get("description", "")
            except ValueError:
                pass
            return ChannelResult(ok=False, error=f"HTTP {r.status_code}: {desc}"[:200])
        return ChannelResult(ok=True)
    except Exception as exc:  # noqa: BLE001 - network failure -> reported, not raised
        return ChannelResult(ok=False, error=str(exc)[:200])


async def _send_webhook(url: str, payload: dict) -> ChannelResult:
    if not url:
        return ChannelResult(ok=False, error="webhook URL not set")
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            r = await client.post(url, json=payload)
        if r.status_code >= 400:
            return ChannelResult(ok=False, error=f"HTTP {r.status_code}")
        return ChannelResult(ok=True)
    except Exception as exc:  # noqa: BLE001
        return ChannelResult(ok=False, error=str(exc)[:200])


async def _deliver(s: NotificationSettings, a: AlertResponse, escalated: bool) -> bool:
    """Push one alert to every enabled channel; True when any channel took it."""
    text = format_message(a, escalated)
    ok = False
    if s.telegram_enabled:
        res = await _send_telegram(s.telegram_chat_id, text)
        ok = ok or res.ok
        if not res.ok:
            logger.warning("telegram delivery failed: %s", res.error)
    if s.webhook_enabled:
        payload = {
            "source": "swdash",
            "escalated": escalated,
            **a.model_dump(mode="json"),
        }
        res = await _send_webhook(s.webhook_url, payload)
        ok = ok or res.ok
        if not res.ok:
            logger.warning("webhook delivery failed: %s", res.error)
    return ok


async def dispatch_pending(db: AsyncSession) -> int:
    """One dispatch pass; returns how many alerts were delivered. Never raises."""
    try:
        s = await get_or_create_settings(db)
        if not (s.telegram_enabled or s.webhook_enabled):
            return 0

        alerts = await _qualifying_alerts(db, s)
        sent = await sent_severities(db, [a.id.removeprefix("alert:") for a in alerts])

        pending: list[tuple[AlertResponse, bool]] = []  # (alert, escalated)
        for a in alerts:
            eid = a.id.removeprefix("alert:")
            prev = sent.get(eid)
            if prev is None:
                pending.append((a, False))
            elif SEVERITY_RANK.get(a.severity, 0) > SEVERITY_RANK.get(prev, 0):
                pending.append((a, True))

        # Oldest first so a backlog reads chronologically; cap per pass.
        pending.sort(key=lambda p: _as_utc(p[0].timestamp))
        pending = pending[: settings.notify_max_per_pass]

        delivered: list[tuple[str, str]] = []
        for a, escalated in pending:
            if await _deliver(s, a, escalated):
                delivered.append((a.id.removeprefix("alert:"), a.severity))
        await record_sent(db, delivered)
        if delivered:
            logger.info("dispatched %d alert notifications", len(delivered))
        return len(delivered)
    except Exception as exc:  # noqa: BLE001 - a dispatch failure must not crash the job
        logger.warning("notification dispatch failed: %s", exc)
        return 0


async def send_test(db: AsyncSession) -> NotificationTestResponse:
    """Send a test message to each *enabled* channel and report per-channel results."""
    s = await get_or_create_settings(db)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    text = f"🛰️ SWDash test notification\nDelivery is working.\n{now}"
    resp = NotificationTestResponse()
    if s.telegram_enabled:
        resp.telegram = await _send_telegram(s.telegram_chat_id, text)
    if s.webhook_enabled:
        resp.webhook = await _send_webhook(
            s.webhook_url,
            {"source": "swdash", "test": True, "message": "SWDash test notification"},
        )
    return resp
