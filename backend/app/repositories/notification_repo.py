"""Read/write helpers for notification settings + the sent-notification ledger."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.notifications import NotificationSettings, SentNotification

_SETTINGS_ID = 1

# Columns settable from the API payload.
_SETTING_FIELDS = (
    "telegram_enabled",
    "telegram_chat_id",
    "webhook_enabled",
    "webhook_url",
    "min_severity",
    "event_types",
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


async def get_or_create_settings(db: AsyncSession) -> NotificationSettings:
    row = await db.get(NotificationSettings, _SETTINGS_ID)
    if row is None:
        row = NotificationSettings(id=_SETTINGS_ID)
        db.add(row)
        await db.commit()
        await db.refresh(row)
    return row


async def save_settings(db: AsyncSession, values: dict) -> NotificationSettings:
    row = await get_or_create_settings(db)
    for f in _SETTING_FIELDS:
        if f in values:
            setattr(row, f, values[f])
    row.updated_at = _utcnow()
    await db.commit()
    await db.refresh(row)
    return row


async def sent_severities(db: AsyncSession, event_ids: list[str]) -> dict[str, str]:
    """{event_id: severity_it_was_sent_at} for the given ids."""
    if not event_ids:
        return {}
    res = await db.execute(
        select(SentNotification).where(SentNotification.event_id.in_(event_ids))
    )
    return {r.event_id: r.severity for r in res.scalars().all()}


async def record_sent(db: AsyncSession, entries: list[tuple[str, str]]) -> None:
    """Upsert (event_id, severity) ledger rows."""
    if not entries:
        return
    now = _utcnow()
    fn = sqlite_insert if db.bind.dialect.name == "sqlite" else pg_insert
    stmt = fn(SentNotification).values(
        [{"event_id": eid, "severity": sev, "sent_at": now} for eid, sev in entries]
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=["event_id"],
        set_={"severity": stmt.excluded.severity, "sent_at": now},
    )
    await db.execute(stmt)
    await db.commit()
