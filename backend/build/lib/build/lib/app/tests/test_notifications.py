"""Tests for alert delivery: settings roundtrip + enable-baseline, dispatch
dedup/escalation/flood-cap, message formatting, and channel senders."""
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient

import app.services.notification_service as notify
from app.config import settings
from app.main import app
from app.schemas.alert_schema import AlertResponse
from app.schemas.notification_schema import ChannelResult

UTC = timezone.utc


def _alert(i: int, severity: str = "warning", hours_ago: float = 1.0,
           type_: str = "xray_flare") -> AlertResponse:
    return AlertResponse(
        id=f"alert:{type_}:2026-07-04T0{i}:00:00+00:00",
        type=type_,
        severity=severity,
        message=f"Test alert {i}",
        timestamp=datetime.now(UTC) - timedelta(hours=hours_ago),
        source="derived",
    )


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


# ── Settings API ─────────────────────────────────────────────────────────────


async def test_settings_roundtrip(client, monkeypatch):
    r = await client.get("/api/notifications/settings")
    assert r.status_code == 200
    body = r.json()
    assert body["telegram_enabled"] is False
    assert body["min_severity"] == "warning"
    assert body["telegram_token_configured"] is False

    monkeypatch.setattr(notify, "get_latest_alerts", AsyncMock(return_value=[]))
    r = await client.put(
        "/api/notifications/settings",
        json={
            "telegram_enabled": True,
            "telegram_chat_id": "12345",
            "min_severity": "watch",
            "event_types": ["xray_flare", "cme"],
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["telegram_enabled"] is True
    assert body["event_types"] == ["xray_flare", "cme"]

    # Bad severity is rejected by validation.
    r = await client.put("/api/notifications/settings", json={"min_severity": "mega"})
    assert r.status_code == 422


async def test_enabling_baselines_existing_alerts(db_session, monkeypatch):
    existing = [_alert(1, "critical"), _alert(2, "warning")]
    monkeypatch.setattr(notify, "get_latest_alerts", AsyncMock(return_value=existing))
    sent_telegram = AsyncMock(return_value=ChannelResult(ok=True))
    monkeypatch.setattr(notify, "_send_telegram", sent_telegram)

    await notify.update_notification_settings(
        db_session,
        {"telegram_enabled": True, "telegram_chat_id": "1", "webhook_enabled": False,
         "webhook_url": "", "min_severity": "warning", "event_types": []},
    )
    # Everything that existed at enable time was baselined - nothing is pushed.
    assert await notify.dispatch_pending(db_session) == 0
    sent_telegram.assert_not_called()


# ── Dispatch ─────────────────────────────────────────────────────────────────


@pytest.fixture
async def enabled(db_session, monkeypatch):
    """Telegram enabled with no pre-existing alerts; sender mocked OK."""
    monkeypatch.setattr(notify, "get_latest_alerts", AsyncMock(return_value=[]))
    await notify.update_notification_settings(
        db_session,
        {"telegram_enabled": True, "telegram_chat_id": "1", "webhook_enabled": False,
         "webhook_url": "", "min_severity": "warning", "event_types": []},
    )
    sender = AsyncMock(return_value=ChannelResult(ok=True))
    monkeypatch.setattr(notify, "_send_telegram", sender)
    return sender


async def test_dispatch_sends_once_then_dedupes(db_session, enabled, monkeypatch):
    monkeypatch.setattr(
        notify, "get_latest_alerts", AsyncMock(return_value=[_alert(1, "warning")])
    )
    assert await notify.dispatch_pending(db_session) == 1
    assert await notify.dispatch_pending(db_session) == 0  # ledger dedupes
    assert enabled.call_count == 1


async def test_dispatch_renotifies_on_escalation(db_session, enabled, monkeypatch):
    monkeypatch.setattr(
        notify, "get_latest_alerts", AsyncMock(return_value=[_alert(1, "warning")])
    )
    await notify.dispatch_pending(db_session)
    # Same event, now critical (e.g. M-flare grew into an X).
    monkeypatch.setattr(
        notify, "get_latest_alerts", AsyncMock(return_value=[_alert(1, "critical")])
    )
    assert await notify.dispatch_pending(db_session) == 1
    text = enabled.call_args.args[1]
    assert "escalated" in text and "CRITICAL" in text


async def test_dispatch_filters_severity_type_and_age(db_session, enabled, monkeypatch):
    alerts = [
        _alert(1, "watch"),                      # below min_severity=warning
        _alert(2, "warning", type_="radio_burst"),
        _alert(3, "critical", hours_ago=settings.notify_lookback_hours + 5),  # too old
    ]
    monkeypatch.setattr(notify, "get_latest_alerts", AsyncMock(return_value=alerts))
    # Restrict to flares only -> even the qualifying radio burst is filtered out.
    await notify.update_notification_settings(
        db_session,
        {"telegram_enabled": True, "telegram_chat_id": "1", "webhook_enabled": False,
         "webhook_url": "", "min_severity": "warning", "event_types": ["xray_flare"]},
    )
    assert await notify.dispatch_pending(db_session) == 0


async def test_dispatch_caps_per_pass(db_session, enabled, monkeypatch):
    many = [_alert(i, "critical", hours_ago=i / 10) for i in range(1, 10)]  # 9 alerts
    monkeypatch.setattr(notify, "get_latest_alerts", AsyncMock(return_value=many))
    assert await notify.dispatch_pending(db_session) == settings.notify_max_per_pass
    # The remainder drains on the next pass.
    assert await notify.dispatch_pending(db_session) == 9 - settings.notify_max_per_pass


async def test_failed_delivery_is_not_marked_sent(db_session, enabled, monkeypatch):
    enabled.return_value = ChannelResult(ok=False, error="boom")
    monkeypatch.setattr(
        notify, "get_latest_alerts", AsyncMock(return_value=[_alert(1, "warning")])
    )
    assert await notify.dispatch_pending(db_session) == 0
    # Sender recovers -> the alert goes out on the next pass.
    enabled.return_value = ChannelResult(ok=True)
    assert await notify.dispatch_pending(db_session) == 1


# ── Channel senders + formatting ─────────────────────────────────────────────


async def test_telegram_requires_token_and_chat_id():
    res = await notify._send_telegram("123", "hi")
    assert res.ok is False and "TELEGRAM_BOT_TOKEN" in res.error


def test_format_message():
    text = notify.format_message(_alert(1, "critical"))
    assert text.startswith("🔴 SWDash CRITICAL")
    assert "Test alert 1" in text and "UTC" in text


async def test_test_endpoint_reports_disabled_channels(client):
    r = await client.post("/api/notifications/test")
    assert r.status_code == 200
    body = r.json()
    assert body["telegram"] is None and body["webhook"] is None
