"""Registry of ingestible sources.

Each entry binds a human-readable name (matching the status endpoint), a target
table, the provenance tag stored on each row, the coroutine that fetches a recent
window of records, and how often to poll it. Services own the fetch/normalize
logic; ingestion just persists what they return.
"""
from dataclasses import dataclass
from typing import Awaitable, Callable

from app.models.timeseries import DstIndex, GoesProton, GoesXrs, KpIndex
from app.services import (
    dst_service,
    goes_proton_service,
    goes_xrs_service,
    kp_service,
)


@dataclass(frozen=True)
class IngestSource:
    name: str                                   # status name, e.g. "GOES-XRS"
    model: type
    source_tag: str                             # value stored in the `source` column
    collect: Callable[[], Awaitable[list[dict]]]
    interval_seconds: int


SOURCES: list[IngestSource] = [
    IngestSource("GOES-XRS", GoesXrs, goes_xrs_service.SOURCE, goes_xrs_service.collect_recent_records, 300),
    IngestSource("GOES-Proton", GoesProton, goes_proton_service.SOURCE, goes_proton_service.collect_recent_records, 300),
    IngestSource("Kp-Index", KpIndex, kp_service.SOURCE, kp_service.collect_recent_records, 3600),
    IngestSource("Dst-Index", DstIndex, dst_service.SOURCE, dst_service.collect_recent_records, 3600),
]
