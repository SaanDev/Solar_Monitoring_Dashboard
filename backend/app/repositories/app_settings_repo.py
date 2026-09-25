"""Read/write helpers for the single-row ``app_settings`` table."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.app_settings import AppSettings

_SETTINGS_ID = 1

# Columns settable from the API payload.
_SETTING_FIELDS = ("radio_burst_binary_model",)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


async def get_or_create_settings(db: AsyncSession) -> AppSettings:
    row = await db.get(AppSettings, _SETTINGS_ID)
    if row is None:
        row = AppSettings(id=_SETTINGS_ID)
        db.add(row)
        await db.commit()
        await db.refresh(row)
    return row


async def save_settings(db: AsyncSession, values: dict) -> AppSettings:
    row = await get_or_create_settings(db)
    for f in _SETTING_FIELDS:
        if f in values:
            setattr(row, f, values[f])
    row.updated_at = _utcnow()
    await db.commit()
    await db.refresh(row)
    return row
