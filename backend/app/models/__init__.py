"""ORM models. Importing this package registers every table on ``Base.metadata``
(used by Alembic autogenerate and by ``create_all`` in tests)."""
from app.models.events import SpaceWeatherEvent
from app.models.radio_detections import RadioBurstDetection
from app.models.source_status import SourceStatus
from app.models.timeseries import (
    HYPERTABLES,
    DstIndex,
    GoesProton,
    GoesXrs,
    KpIndex,
)

__all__ = [
    "GoesXrs",
    "GoesProton",
    "KpIndex",
    "DstIndex",
    "SourceStatus",
    "SpaceWeatherEvent",
    "RadioBurstDetection",
    "HYPERTABLES",
]
