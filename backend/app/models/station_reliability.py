"""Per-station track record for the multi-station burst confirmation.

A burst is only confirmed when independent stations agree on it, and each
station's reading is weighted by its track record: how its readings look during
real bursts versus by chance (``app.processing.burst_confirmation``). This table
holds what the daily measurement found for each station, and the operator's
override from the Settings page.

The measured columns are rewritten by every recomputation; ``override`` is the
only user setting and survives them:

* ``auto`` — the station's readings carry the evidence its record earns;
* ``always`` — its flags weigh at least as much as a typical reliable station's;
* ``never`` — it is ignored entirely.

The table is a cache of the measurement, never a source of truth: dropping it
falls back to the built-in priors until the next recomputation (overrides aside).
"""
from datetime import datetime, timezone

from sqlalchemy import JSON, Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base, UTCDateTime

OVERRIDE_AUTO = "auto"
OVERRIDE_ALWAYS = "always"
OVERRIDE_NEVER = "never"
OVERRIDES = (OVERRIDE_AUTO, OVERRIDE_ALWAYS, OVERRIDE_NEVER)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class StationReliability(Base):
    __tablename__ = "radio_station_reliability"

    station: Mapped[str] = mapped_column(String(64), primary_key=True)
    override: Mapped[str] = mapped_column(
        String(8), nullable=False, default=OVERRIDE_AUTO, server_default=OVERRIDE_AUTO
    )
    # Model whose detections the measurement below came from ("" = never measured).
    model_id: Mapped[str] = mapped_column(String(32), nullable=False, default="", server_default="")
    # Sun-up files scored / labelled Burst in the measurement window.
    files: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    bursts: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    # Bursts that could be judged (enough other sites observing), and how many
    # of those >= 2 other sites also flagged.
    judged: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    confirmed: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    chance_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    # Agreement beyond chance in this window (null: nothing could be judged).
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    # Share of its sun-up observing time flagged at high confidence.
    duty: Mapped[float | None] = mapped_column(Float, nullable=True)
    observed_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    # Minutes per reading category (silent, low, mid, high) while observing, and
    # during anchor bursts (other reliable sites confirming on their own) — what
    # its readings look like by chance vs during a real burst.
    null_counts: Mapped[list | None] = mapped_column(JSON, nullable=True)
    anchor_counts: Mapped[list | None] = mapped_column(JSON, nullable=True)
    computed_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), default=_utcnow, onupdate=_utcnow, nullable=False
    )
