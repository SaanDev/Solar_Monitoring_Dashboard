"""Registry of the burst-classification models the dashboard can run.

Three checkpoints ship, all ResNet-18 based and all trained in the CALLISTO
Trainer project:

* **CCM v1.0.0** — the original binary burst / no-burst classifier. Kept
  byte-for-byte as it was: same checkpoint, same threshold, same header-derived
  frequency metadata, so results stay comparable with everything already stored.
* **CCM v1.1.0** — the newer binary classifier (val F1 0.920, test F1 0.932).
  Same architecture, so it loads through the same builder; a lower tuned
  threshold (0.51) and ``AXES``-table frequency metadata, which is what it was
  actually trained on.
* **CCMT v1.0.0** — burst *type* classifier: 3-class softmax over
  ``Type II / Type III / Other``. Image-only (no metadata branch) and trained on
  hand-drawn crops around single bursts, so it runs as a **second stage** on
  region crops of files a binary model already called ``Burst`` — never on a
  whole file, and never as a detector of its own.

This module owns model *identity* (ids, names, paths, thresholds, published
metrics). Loading and scoring live in :mod:`app.ml.inference`.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

ModelKind = Literal["binary", "type"]
# Where a model's freq_min / freq_max metadata features come from:
#   "header" — CRVAL2/CDELT2 from the primary header (what the dashboard has
#              always done; keeps CCM v1.0.0 unchanged).
#   "axes"   — the FITS AXES bintable's FREQUENCY column, which is what the
#              training pipeline used, falling back to the header when absent.
FreqSource = Literal["header", "axes"]


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
    freq_source: FreqSource = "header"
    # Fallback classes, in label order. The authoritative map is read from the
    # checkpoint's ``data.classes``; this is only used if it is missing.
    classes: tuple[str, ...] = ()
    # Published evaluation numbers, surfaced in the UI so the choice is informed.
    metrics: dict[str, Any] = field(default_factory=dict)

    @property
    def version(self) -> str:
        return self.id.rsplit("-", 1)[-1]


CCM_V100 = ModelSpec(
    id="ccm-1.0.0",
    name="CCM v1.0.0",
    full_name="CALLISTO Classifier Model v1.0.0",
    kind="binary",
    path_setting="ml_model_path",
    url_setting="ml_model_url",
    description=(
        "Original binary burst / no-burst classifier. ResNet-18 with a "
        "station/frequency/date metadata branch, tuned threshold 0.595."
    ),
    freq_source="header",
    classes=("No_Burst", "Burst"),
    metrics={"threshold": 0.595},
)

CCM_V110 = ModelSpec(
    id="ccm-1.1.0",
    name="CCM v1.1.0",
    full_name="CALLISTO Classifier Model v1.1.0",
    kind="binary",
    path_setting="ml_ccm_v110_path",
    url_setting="ml_ccm_v110_url",
    description=(
        "Retrained binary burst / no-burst classifier. Same architecture as "
        "v1.0.0 with a lower tuned threshold (0.51) and frequency features read "
        "from the FITS AXES table, matching how it was trained."
    ),
    freq_source="axes",
    classes=("No_Burst", "Burst"),
    metrics={
        "threshold": 0.51,
        "val_f1": 0.9197,
        "val_accuracy": 0.9433,
        "val_roc_auc": 0.9840,
        "test_f1": 0.9315,
        "test_accuracy": 0.9485,
        "test_roc_auc": 0.9910,
    },
)

CCMT_V100 = ModelSpec(
    id="ccmt-1.0.0",
    name="CCMT v1.0.0",
    full_name="CALLISTO Classifier Model by Types v1.0.0",
    kind="type",
    path_setting="ml_ccmt_v100_path",
    url_setting="ml_ccmt_v100_url",
    description=(
        "Burst-type classifier (Type II / Type III / Other). Image-only "
        "ResNet-18 trained on crops around single bursts, so it runs on bright "
        "region proposals inside files a binary model already flagged as a "
        "burst. It has no background class and is not a detector."
    ),
    freq_source="axes",
    classes=("Type II", "Type III", "Other"),
    metrics={
        "val_accuracy": 0.9655,
        "val_macro_f1": 0.8888,
        "val_f1_type_ii": 0.9286,
        "val_f1_type_iii": 0.9877,
        "val_f1_other": 0.75,
    },
)

_SPECS: dict[str, ModelSpec] = {
    spec.id: spec for spec in (CCM_V100, CCM_V110, CCMT_V100)
}


# ── Lookup ────────────────────────────────────────────────────────────────────


def list_specs(kind: ModelKind | None = None) -> list[ModelSpec]:
    specs = list(_SPECS.values())
    return [s for s in specs if kind is None or s.kind == kind]


def get_spec(model_id: str) -> ModelSpec:
    try:
        return _SPECS[model_id]
    except KeyError:
        known = ", ".join(sorted(_SPECS))
        raise UnknownModelError(f"unknown model '{model_id}' (known: {known})") from None


def resolve_binary(model_id: str | None = None) -> ModelSpec:
    """The binary model to use: an explicit id, else the configured default.

    A configured default that is somehow invalid falls back to CCM v1.0.0 rather
    than breaking every scan — a typo in ``RADIO_BURST_BINARY_MODEL`` should
    degrade to the shipped model, not disable burst detection.
    """
    if model_id:
        spec = get_spec(model_id)
        if spec.kind != "binary":
            raise UnknownModelError(f"'{model_id}' is not a binary model")
        return spec

    from app.config import settings

    configured = (settings.radio_burst_binary_model or "").strip()
    try:
        spec = get_spec(configured)
    except UnknownModelError:
        return CCM_V100
    return spec if spec.kind == "binary" else CCM_V100


def resolve_type(model_id: str | None = None) -> ModelSpec:
    """The type model to use: an explicit id, else the configured default."""
    if model_id:
        spec = get_spec(model_id)
        if spec.kind != "type":
            raise UnknownModelError(f"'{model_id}' is not a burst-type model")
        return spec

    from app.config import settings

    configured = (settings.radio_burst_type_model or "").strip()
    try:
        spec = get_spec(configured)
    except UnknownModelError:
        return CCMT_V100
    return spec if spec.kind == "type" else CCMT_V100


def classify_types_default() -> bool:
    from app.config import settings

    return bool(settings.radio_burst_classify_types)


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

    Each binary model has its own tuned decision threshold, so a single global
    figure cannot serve both: 0.595 (CCM v1.0.0's) would silently drop every
    CCM v1.1.0 detection between 0.51 and 0.595. So the model's own threshold is
    the default, and ``RADIO_BURST_ALERT_MIN_PROBABILITY`` becomes an explicit
    override for gating *above* it.
    """
    from app.config import settings
    from app.ml.inference import model_threshold

    override = float(settings.radio_burst_alert_min_probability or 0.0)
    if override > 0:
        return override
    return model_threshold(spec)
