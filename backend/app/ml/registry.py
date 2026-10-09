"""Registry of the burst models the dashboard can run.

One model ships: **BnB v1.1**, a whole-file burst / no-burst classifier trained
in the CALLISTO Trainer. It answers one question per segment — is there a burst
in it — and does not name the burst's type.

It replaced BnB v1.0 — the same network, retrained on 2026 recordings — which
had replaced CCM v2.0 / v2.0.1, a unified region model that also typed bursts,
and before it the CCM v1.0.0 / v1.1.0 binary classifiers and the separate CCMT
v1.0.0 type model. Their ids live on only in :data:`RETIRED_MODELS`, because
detections they stored stay in the database until the backfill re-scores them,
and each such row must still be judged by the threshold of the model that made
it.

This module owns model *identity* (ids, names, paths, thresholds, published
metrics) and which model is currently active — the Settings-page selection,
applied through :func:`set_model_selection` and persisted by
:mod:`app.services.model_settings_service`. Loading and scoring live in
:mod:`app.ml.inference`.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

# "binary": whole-file burst / no-burst, no burst type.
ModelKind = Literal["binary"]


class UnknownModelError(ValueError):
    """Raised when a caller asks for a model id that is not registered."""


@dataclass(frozen=True)
class ModelSpec:
    id: str
    name: str
    full_name: str
    kind: ModelKind
    # Attribute on ``Settings`` holding this checkpoint's path.
    path_setting: str
    # Attribute on ``Settings`` holding an optional direct download URL.
    url_setting: str
    description: str
    # The burst types the model reports; empty for a model that does not type.
    classes: tuple[str, ...] = ()
    # Published evaluation numbers, surfaced in the UI so the choice is informed.
    metrics: dict[str, Any] = field(default_factory=dict)

    @property
    def version(self) -> str:
        return self.id.rsplit("-", 1)[-1]


BNB_V110 = ModelSpec(
    id="bnb-1.1.0",
    name="BnB v1.1",
    full_name="Burst / No-Burst classifier v1.1",
    kind="binary",
    path_setting="ml_model_path",
    url_setting="ml_model_url",
    description=(
        "Whole-file burst / no-burst classifier. A ResNet-34 reads the whole "
        "15-minute spectrum, and a small metadata branch adds the station, "
        "frequency range and date. It says whether a segment holds a burst, not "
        "which type."
    ),
    metrics={
        # Tuned on the validation split; the loader reads the same value from
        # the checkpoint and warns on mismatch.
        "threshold": 0.786865234375,
        # File-level at the threshold, validation split (345 files, 151 bursts).
        "val_precision": 0.9858,
        "val_recall": 0.9205,
        "val_f1": 0.9521,
        "val_false_alarm_rate": 0.0103,
        # Test split (322 files, 124 bursts), never seen in training or tuning,
        # scored through this port (which reproduces the validation counts above
        # exactly).
        "test_precision": 0.9725,
        "test_recall": 0.8548,
        "test_false_alarm_rate": 0.0152,
        # Held-out files from the Trainer's Burst List folders, none in v1.1's
        # training set (measured 2026-10-09): labelled bursts flagged (3,255
        # Type II/III/IV/V/CTM/J files), and quiet files flagged in the NO_BURST
        # folder (~96% quiet by hand labels) — 4,912 from the 50 trained
        # stations, 1,997 from others. BnB v1.0 on the same files: 0.608, 0.069,
        # 0.111 (some may have been in its training set). The extra on unseen
        # stations comes from a few cluttered ones (INDIA-OOTY, MEXICO-LANCE,
        # MEXART, ...). The station input itself moves a file's probability by
        # ~0.004 (3,000 files; 0.2% verdicts flip), so an unseen station's
        # untrained slot is harmless.
        "heldout_bursts_flagged": 0.570,
        "heldout_quiet_flagged_trained_stations": 0.066,
        "heldout_quiet_flagged_other_stations": 0.103,
    },
)

_SPECS: dict[str, ModelSpec] = {spec.id: spec for spec in (BNB_V110,)}

# Models that used to ship: id -> (name, decision threshold). Kept so detections
# they stored are still gated and labelled correctly until re-scored.
RETIRED_MODELS: dict[str, tuple[str, float]] = {
    "ccm-1.0.0": ("CCM v1.0.0", 0.595),
    "ccm-1.1.0": ("CCM v1.1.0", 0.51),
    "ccm-2.0.0": ("CCM v2.0", 0.7975836745463312),
    "ccm-2.0.1": ("CCM v2.0.1", 0.7975836745463312),
    "bnb-1.0.0": ("BnB v1.0", 0.5634765625),
}


# ── Lookup ────────────────────────────────────────────────────────────────────


def list_specs() -> list[ModelSpec]:
    return list(_SPECS.values())


def get_spec(model_id: str) -> ModelSpec:
    try:
        return _SPECS[model_id]
    except KeyError:
        known = ", ".join(sorted(_SPECS))
        raise UnknownModelError(f"unknown model '{model_id}' (known: {known})") from None


def model_display_name(model_id: str | None) -> str:
    """A model's name for display, including a retired model's; the id otherwise."""
    if not model_id:
        return ""
    if model_id in _SPECS:
        return _SPECS[model_id].name
    if model_id in RETIRED_MODELS:
        return RETIRED_MODELS[model_id][0]
    return model_id


# ── Selected model (Settings page) ────────────────────────────────────────────

# The model chosen from the dashboard's Settings page, applied for the life of
# this process. It is persisted in ``app_settings`` and re-applied on startup
# (see app/services/model_settings_service.py); holding it here as a
# process-global is what keeps ``resolve_model`` synchronous, so the scheduler,
# the inference layer and request handlers all read the same choice without any
# of them needing a DB session. Single-process deployment assumed — the backend
# runs one uvicorn worker with the scheduler in it.
_selection: str | None = None


def set_model_selection(model_id: str | None) -> ModelSpec | None:
    """Point every default-model lookup at ``model_id`` until it changes again.

    Validates before applying — an unknown id raises rather than silently
    degrading, because unlike a stale env var this comes from a user action that
    deserves an error message. ``None`` or ``""`` clears the selection, falling
    back to ``RADIO_BURST_MODEL``.
    """
    global _selection

    cleaned = (model_id or "").strip()
    if not cleaned:
        _selection = None
        return None
    spec = get_spec(cleaned)
    _selection = spec.id
    return spec


def model_selection() -> str | None:
    """The selected model id, or None when following configuration."""
    return _selection


def resolve_model(model_id: str | None = None) -> ModelSpec:
    """The model to use: an explicit id, else the selected/configured one.

    Precedence is explicit argument > Settings-page selection > env default.

    A configured default that is somehow invalid (a typo, or a retired model's
    id left in an old .env) falls back to BnB v1.1 rather than breaking every
    scan.
    """
    if model_id:
        return get_spec(model_id)
    if _selection:
        # Validated in set_model_selection, so this cannot raise in practice.
        return get_spec(_selection)

    from app.config import settings

    try:
        return get_spec((settings.radio_burst_model or "").strip())
    except UnknownModelError:
        return BNB_V110


# ── Checkpoint location ───────────────────────────────────────────────────────

# backend/ — relative checkpoint paths resolve from here.
_BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent


def checkpoint_path(spec: ModelSpec) -> Path:
    from app.config import settings

    raw = getattr(settings, spec.path_setting, "") or ""
    path = Path(raw)
    return path if path.is_absolute() else _BACKEND_ROOT / path


def checkpoint_url(spec: ModelSpec) -> str:
    from app.config import settings

    return (getattr(settings, spec.url_setting, "") or "").strip()


def is_available(spec: ModelSpec) -> bool:
    """Whether the checkpoint file is present and not a Git LFS pointer.

    Cheap enough to call per request (a ``stat`` plus, for small files, a 39-byte
    read), and it lets the UI grey out a model instead of failing mid-scan.
    """
    from app.ml.inference import is_lfs_pointer

    path = checkpoint_path(spec)
    return path.exists() and not is_lfs_pointer(path)


# ── Thresholds ────────────────────────────────────────────────────────────────


def alert_min_probability(spec: ModelSpec) -> float:
    """Minimum probability for a detection to contribute to an alert/event.

    The model's own tuned threshold, unless
    ``RADIO_BURST_ALERT_MIN_PROBABILITY`` explicitly overrides it to gate higher.
    """
    from app.config import settings
    from app.ml.inference import model_threshold

    override = float(settings.radio_burst_alert_min_probability or 0.0)
    if override > 0:
        return override
    return model_threshold(spec)


def alert_min_probability_for(model_id: str | None) -> float:
    """:func:`alert_min_probability` for whichever model stored a detection row.

    A retired model's rows are gated by that model's own threshold — one
    threshold for every row would judge BnB v1.0's 0.6 burst (over its 0.56) a
    miss by BnB v1.1's 0.79. An empty or unknown id means the active model.
    """
    if model_id in RETIRED_MODELS:
        from app.config import settings

        override = float(settings.radio_burst_alert_min_probability or 0.0)
        return override if override > 0 else RETIRED_MODELS[model_id][1]
    try:
        spec = get_spec(model_id) if model_id else resolve_model()
    except UnknownModelError:
        spec = resolve_model()
    return alert_min_probability(spec)
