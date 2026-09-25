"""ORM models. Importing this package registers every table on ``Base.metadata``
(used by Alembic autogenerate and by ``create_all`` in tests)."""
from app.models.app_settings import AppSettings
from app.models.cme import CmeEvent
from app.models.events import SpaceWeatherEvent
from app.models.notifications import NotificationSettings, SentNotification
from app.models.radio_backfill import RadioBurstBackfillDay
from app.models.radio_detections import RadioBurstDetection
from app.models.source_status import SourceStatus
from app.models.timeseries import (
    HYPERTABLES,
    DstIndex,
    GoesElectron,
    GoesMagnetometer,
    GoesProton,
    GoesXrs,
    KpIndex,
)

__all__ = [
    "GoesXrs",
    "GoesProton",
    "GoesElectron",
    "GoesMagnetometer",
    "KpIndex",
    "DstIndex",
    "SourceStatus",
    "SpaceWeatherEvent",
    "RadioBurstDetection",
    "RadioBurstBackfillDay",
    "CmeEvent",
    "NotificationSettings",
    "SentNotification",
    "AppSettings",
    "HYPERTABLES",
]
