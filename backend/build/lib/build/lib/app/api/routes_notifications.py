"""Alert-delivery preferences + test endpoint (Telegram / webhook push)."""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas.notification_schema import (
    NotificationSettingsPayload,
    NotificationSettingsResponse,
    NotificationTestResponse,
)
from app.services.notification_service import (
    get_notification_settings,
    send_test,
    update_notification_settings,
)

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


@router.get("/settings", response_model=NotificationSettingsResponse)
async def read_settings(db: AsyncSession = Depends(get_db)) -> NotificationSettingsResponse:
    """Current delivery preferences (the bot token itself is never returned)."""
    return await get_notification_settings(db)


@router.put("/settings", response_model=NotificationSettingsResponse)
async def write_settings(
    payload: NotificationSettingsPayload, db: AsyncSession = Depends(get_db)
) -> NotificationSettingsResponse:
    """Save delivery preferences. Turning delivery on baselines the ledger so
    only events occurring after enabling are pushed."""
    return await update_notification_settings(db, payload.model_dump())


@router.post("/test", response_model=NotificationTestResponse)
async def test_channels(db: AsyncSession = Depends(get_db)) -> NotificationTestResponse:
    """Send a test message to every enabled channel."""
    return await send_test(db)
