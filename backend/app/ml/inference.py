"""In-process CCM v2.0 burst model — load it once and score FITS bytes.

Models are loaded lazily on first use (or eagerly at startup via ``warm_up()``)
and then kept in memory, one entry per model id, for the lifetime of the backend
process. :mod:`app.ml.registry` owns which ids exist and where their checkpoints
live.

## How a file is scored

CCM v2.0 was trained on regions, not whole files, so scoring mirrors the
CALLISTO Trainer's ``CascadePredictor`` step for step:

1. the whole spectrum is normalized, plus a twin with a quiet-part background;
2. candidate regions are located (:mod:`app.ml.regions`) with the finder
   settings the checkpoint was calibrated with;
3. each region becomes three 224x224 views and 28 measured features;
4. the model gives each region a probability for No_Burst, RFI and every burst
   type;
5. the burst-type probabilities are corrected toward how often each type really
   occurs (the checkpoint's calibrated type priors). This only moves probability
   *between* burst types, so the burst decision below is unaffected;
6. a region is a burst when its **burst evidence** — ``1 - P(No_Burst) - P(RFI)``
   — reaches the checkpoint's calibrated threshold, and a file is a burst when
   any region is. The file's burst probability is its strongest region's
   evidence.

What is *reported* folds classes together: RFI is a kind of background, and a
Type IIIG (a group of Type III bursts) is a Type III. The folding adds the
probabilities before the type is chosen, so a region split between Type III and
Type IIIG is called Type III even when neither alone is the largest class.

The finder fires on interference and calibration artifacts as readily as on
bursts, and in quiet files as often as in burst files; that is fine here,
because unlike the old type-only model this one has background and RFI classes
and rejects them itself.
"""
from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from app.ml.physics import measure_burst
from app.ml.preprocessing import (
    CropConfig,
    SpectrumAxes,
    normalize_full_spectrum,
    quiet_normalized_spectrum,
    read_spectrum_bytes,
    region_views,
)
from app.ml.region_features import (
    FEATURE_COUNT,
    FEATURE_SET_REGION_V2,
    feature_vector,
    file_context,
    measure_region,
)
from app.ml.regions import (
    DEFAULT_HYSTERESIS,
    DEFAULT_MAX_REGIONS,
    DEFAULT_MIN_AREA,
    DEFAULT_REGION_THRESHOLD,
    Region,
    find_candidate_regions,
    region_to_axes,
    resolve_threshold,
)
from app.ml.registry import ModelSpec

logger = logging.getLogger(__name__)

NO_BURST = "No_Burst"
RFI = "RFI"
TYPE_III = "Type III"
TYPE_IIIG = "Type IIIG"
# Classes meaning "this region is not a burst".
NON_BURST_CLASSES = (NO_BURST, RFI)
# Model classes reported as another class: RFI is a kind of background, and a
# Type IIIG is a group of Type III bursts.
REPORTED_AS = {RFI: NO_BURST, TYPE_IIIG: TYPE_III}

# Regions are classified in batches of this many (the finder caps a file at 24).
BATCH_SIZE = 32


@dataclass
class LoadedModel:
    """One loaded checkpoint plus everything scoring needs from its config."""

    spec: ModelSpec
    model: Any
    config: dict[str, Any]
    device: Any
    # Calibrated burst-evidence threshold.
    threshold: float
    # The model's own classes, in output order.
    class_names: tuple[str, ...]
    views: tuple[str, ...]
    crop: CropConfig
    preprocessing: dict[str, Any]
    # Region-finder settings the threshold was calibrated with.
    finder: dict[str, Any]
    # Type-frequency correction: log(observed / training share) per burst class,
    # applied with ``type_strength`` (0 = types as trained).
    type_adjustment: dict[str, float] = field(default_factory=dict)
    type_strength: float = 0.0


@dataclass
class ScoredRegion:
    """One candidate region and the verdict on it."""

    region: Region
    # Reported classes (RFI folded into No_Burst, Type IIIG into Type III).
    probabilities: dict[str, float]
    burst_evidence: float
    is_burst: bool
    burst_type: str | None = None
    # Confidence in the type *given* that the region is a burst.
    type_confidence: float | None = None


# model id -> LoadedModel. Shared across all requests.
_MODELS: dict[str, LoadedModel] = {}
# Model ids whose load already failed, so a broken checkpoint is not retried on
# every single file of a scan (the reason is logged once).
_FAILED: set[str] = set()
# Inference is not guaranteed thread-safe in all torch backends; serialise.
_PREDICT_LOCK = threading.Lock()
# Prevent concurrent model-load attempts (e.g. two requests at cold start).
_LOAD_LOCK = threading.Lock()


def _resolve_device() -> "torch.device":
    import torch
    from app.config import settings

    requested = getattr(settings, "ml_inference_device", "auto").strip().lower()
    if requested == "cpu":
        return torch.device("cpu")
    if requested == "cuda":
        return torch.device("cuda")
    if requested == "mps":
        return torch.device("mps")
    # auto: prefer CUDA > MPS (Apple Silicon) > CPU
    if torch.cuda.is_available():
        return torch.device("cuda")
    if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
        return torch.device("mps")
    return torch.device("cpu")


def _torch_load(path: str | Path, device: "torch.device") -> dict[str, Any]:
    import torch
    try:
        return torch.load(path, map_location=device, weights_only=False)
    except TypeError:
        return torch.load(path, map_location=device)


# Git LFS stores a tiny text pointer in place of the real file until `git lfs
# pull` runs. Detect that so the user gets a clear instruction instead of an
# opaque torch deserialisation error.
_LFS_POINTER_MAGIC = b"version https://git-lfs.github.com/spec"


def is_lfs_pointer(path: Path) -> bool:
    try:
        if path.stat().st_size > 1024:  # real checkpoints are 40+ MB
            return False
        with open(path, "rb") as fh:
            return fh.read(len(_LFS_POINTER_MAGIC)) == _LFS_POINTER_MAGIC
    except OSError:
        return False


# ─── Load ─────────────────────────────────────────────────────────────────────


def _class_names(config: dict[str, Any]) -> tuple[str, ...]:
    """Class names ordered by label id, from the checkpoint's ``data.classes``."""
    classes = (config.get("data", {}) or {}).get("classes") or {}
    return tuple(name for name, _ in sorted(classes.items(), key=lambda kv: int(kv[1])))


def _finder_settings(inference_cfg: dict[str, Any]) -> dict[str, Any]:
    recorded = inference_cfg.get("region_finder") or {}
    return {
        "threshold": float(recorded.get("threshold", DEFAULT_REGION_THRESHOLD)),
        "adaptive": bool(recorded.get("adaptive", True)),
        "min_area": int(recorded.get("min_area", DEFAULT_MIN_AREA)),
        "max_regions": int(recorded.get("max_regions", DEFAULT_MAX_REGIONS)),
        # A recorded None means plain thresholding; absent means the default.
        "hysteresis": recorded.get("hysteresis", DEFAULT_HYSTERESIS),
    }


def _load(spec: ModelSpec, checkpoint_path: Path) -> LoadedModel:
    """Load a checkpoint into a :class:`LoadedModel` (no caching)."""
    from app.ml.model import build_model

    device = _resolve_device()
    checkpoint = _torch_load(checkpoint_path, device)
    config = checkpoint["config"]
    model_cfg = config["model"]

    class_names = _class_names(config)
    if NO_BURST not in class_names:
        raise ValueError(f"not a unified model: its classes are {list(class_names)}")
    if not model_cfg.get("use_physics") or model_cfg.get("feature_set") != FEATURE_SET_REGION_V2:
        raise ValueError(
            f"expected the {FEATURE_SET_REGION_V2!r} feature set, got "
            f"{model_cfg.get('feature_set')!r}"
        )

    model = build_model(model_cfg, num_classes=len(class_names), num_features=FEATURE_COUNT)
    model.load_state_dict(checkpoint["model_state"])
    model.to(device)
    model.eval()

    inference_cfg = config.get("inference", {}) or {}
    published = float(spec.metrics.get("threshold", 0.5))
    calibrated = inference_cfg.get("burst_threshold")
    if calibrated is None:
        logger.warning(
            "%s: checkpoint has no calibrated burst threshold — using the registry's %.4f",
            spec.name, published,
        )
        threshold = published
    else:
        threshold = float(calibrated)
        if abs(threshold - published) > 1e-6:
            # The registry publishes the threshold for the UI and for gating
            # before the model is loaded; a mismatch means one of them is stale.
            logger.warning(
                "%s: checkpoint threshold %.4f differs from the registry's %.4f — "
                "using the checkpoint's",
                spec.name, threshold, published,
            )

    priors = inference_cfg.get("type_priors") or {}
    adjustment = {str(k): float(v) for k, v in (priors.get("adjustment") or {}).items()}
    strength = priors.get("strength")
    loaded = LoadedModel(
        spec=spec,
        model=model,
        config=config,
        device=device,
        threshold=threshold,
        class_names=class_names,
        views=tuple(model_cfg.get("views") or ("crop",)),
        crop=CropConfig.from_config(config),
        preprocessing=config["preprocessing"],
        finder=_finder_settings(inference_cfg),
        type_adjustment=adjustment,
        type_strength=float(strength) if adjustment and isinstance(strength, (int, float)) else 0.0,
    )
    logger.info(
        "%s loaded on %s (threshold=%.4f, classes=%s, views=%s, type-prior strength=%.2f)",
        spec.name, device, threshold, ", ".join(class_names), ", ".join(loaded.views),
        loaded.type_strength,
    )
    return loaded


def _download(spec: ModelSpec, dest: Path) -> None:
    """Download a checkpoint from its configured URL."""
    from app.ml.registry import checkpoint_url

    url = checkpoint_url(spec)
    if not url:
        raise RuntimeError(
            f"{spec.name} checkpoint not found. It normally ships in the repo via "
            "Git LFS — run 'git lfs install && git lfs pull'. (Alternatively set "
            f"{spec.url_setting.upper()} in .env and run "
            f"'python scripts/download_model.py --model {spec.id}'.)"
        )
    import urllib.request

    dest.parent.mkdir(parents=True, exist_ok=True)
    logger.info("Downloading %s checkpoint from %s …", spec.name, url)
    urllib.request.urlretrieve(url, dest)
    logger.info("Checkpoint saved to %s", dest)


# ─── Public API ───────────────────────────────────────────────────────────────


def get_loaded(spec: ModelSpec) -> LoadedModel | None:
    """Load ``spec`` if needed and return it, or None when unavailable.

    Unavailable is not an error here: a missing checkpoint, an unpulled LFS
    pointer or a torch-less install all disable that model with a warning, the
    same way the feature has always degraded.
    """
    cached = _MODELS.get(spec.id)
    if cached is not None:
        return cached
    if spec.id in _FAILED:
        return None

    from app.config import settings
    from app.ml.registry import checkpoint_path

    try:
        import torch  # noqa: F401
    except ImportError:
        logger.warning(
            "PyTorch not installed — burst detection disabled. "
            "Install with: pip install -e '.[ml]'"
        )
        _FAILED.add(spec.id)
        return None

    with _LOAD_LOCK:
        cached = _MODELS.get(spec.id)  # another thread may have won the race
        if cached is not None:
            return cached
        if spec.id in _FAILED:
            return None

        path = checkpoint_path(spec)

        # File present but it's still a Git LFS pointer (cloned without LFS).
        if path.exists() and is_lfs_pointer(path):
            logger.warning(
                "%s checkpoint at %s is a Git LFS pointer, not the real file. "
                "Run 'git lfs install && git lfs pull' to fetch it — "
                "this model is unavailable until then.",
                spec.name, path,
            )
            _FAILED.add(spec.id)
            return None

        if not path.exists():
            if not getattr(settings, "ml_model_auto_download", True):
                logger.warning(
                    "%s checkpoint not found at %s — model unavailable.", spec.name, path
                )
                _FAILED.add(spec.id)
                return None
            try:
                _download(spec, path)
            except Exception as exc:
                logger.error("Failed to download %s checkpoint: %s", spec.name, exc)
                _FAILED.add(spec.id)
                return None

        try:
            loaded = _load(spec, path)
        except Exception as exc:
            logger.error("Failed to load %s: %s", spec.name, exc)
            _FAILED.add(spec.id)
            return None
        _MODELS[spec.id] = loaded
        return loaded


def ensure_model_loaded(model_id: str | None = None) -> bool:
    """Load a model (the active one unless given). True on success."""
    from app.ml.registry import resolve_model

    return get_loaded(resolve_model(model_id)) is not None


def model_threshold(spec: ModelSpec) -> float:
    """A model's decision threshold, without forcing a load.

    Reads the loaded model when it is in memory, otherwise the threshold the
    registry publishes — so alert gating can be computed before the first score.
    """
    loaded = _MODELS.get(spec.id)
    if loaded is not None:
        return loaded.threshold
    return float(spec.metrics.get("threshold", 0.5))


def model_state() -> dict[str, Any]:
    """Per-model load state, for health reporting."""
    return {
        model_id: {
            "name": loaded.spec.name,
            "kind": loaded.spec.kind,
            "device": str(loaded.device),
            "threshold": loaded.threshold,
            "classes": list(loaded.class_names),
        }
        for model_id, loaded in _MODELS.items()
    }


def warm_up() -> None:
    """Eagerly load the model the scanner will use (non-fatal — logs on failure)."""
    from app.ml.registry import resolve_model

    get_loaded(resolve_model())


def probability_to_alert_level(probability: float) -> str:
    if probability < 0.50:
        return "No alert"
    if probability < 0.80:
        return "Possible burst"
    if probability < 0.90:
        return "Likely burst"
    return "High-confidence burst"


def relative_alert_level(probability: float, threshold: float | None) -> str:
    """Alert wording relative to the decision threshold, not to a fixed 0.5.

    With a calibrated threshold near 0.8, evidence of 0.7 would read "Possible
    burst" on the fixed bands while the verdict beside it says No_Burst. So the
    evidence is rescaled for the bands, mapping the threshold to 0.5.
    """
    if threshold is None or not 0.0 < threshold < 1.0:
        return probability_to_alert_level(probability)
    if probability >= threshold:
        scaled = 0.5 + 0.5 * (probability - threshold) / (1.0 - threshold)
    else:
        scaled = 0.5 * probability / threshold
    return probability_to_alert_level(float(scaled))


# ─── Scoring ──────────────────────────────────────────────────────────────────


def adjust_type_probabilities(
    probabilities: np.ndarray,
    class_names: tuple[str, ...],
    adjustment: dict[str, float],
    strength: float,
) -> np.ndarray:
    """Shift the burst-type probabilities toward how often each type occurs.

    ``p'(type) ~ p(type) * exp(strength * adjustment[type])``, rescaled so the
    burst types keep their total: non-burst classes, burst evidence and every
    threshold calibrated on it are exactly what they were.
    """
    probabilities = np.asarray(probabilities, dtype=np.float64)
    if not adjustment or strength <= 0 or probabilities.size == 0:
        return probabilities
    burst = [i for i, name in enumerate(class_names) if name in adjustment]
    if not burst:
        return probabilities
    factors = np.exp(float(strength) * np.array([adjustment[class_names[i]] for i in burst]))
    part = probabilities[:, burst]
    mass = part.sum(axis=1, keepdims=True)
    shifted = part * factors[None, :]
    shifted_mass = shifted.sum(axis=1, keepdims=True)
    scale = np.divide(mass, shifted_mass, out=np.zeros_like(mass), where=shifted_mass > 0)
    adjusted = probabilities.copy()
    adjusted[:, burst] = shifted * scale
    return adjusted


def region_probabilities(
    loaded: LoadedModel,
    normalized: np.ndarray,
    quiet: np.ndarray | None,
    axes: SpectrumAxes,
    rfi_channels: Any,
    regions: list[Region],
) -> np.ndarray:
    """``[N, K]`` class probabilities for ``regions``, type priors applied."""
    import torch

    if not regions:
        return np.zeros((0, len(loaded.class_names)))
    context = file_context(normalized, axes, rfi_channels)
    images, features = [], []
    for region in regions:
        box = region.as_box()
        images.append(region_views(normalized, box, loaded.crop, loaded.views, quiet=quiet))
        # Physics is measured on the same pixels for every class, background
        # included, so a measurement's presence never gives the label away.
        physics = measure_burst(normalized, axes, box.row0, box.row1, box.col0, box.col1)
        measured = measure_region(context, box.row0, box.row1, box.col0, box.col1, physics)
        features.append(feature_vector(physics, measured))

    chunks: list[np.ndarray] = []
    for start in range(0, len(regions), BATCH_SIZE):
        image = np.stack(images[start:start + BATCH_SIZE])
        vector = np.stack(features[start:start + BATCH_SIZE])
        with _PREDICT_LOCK, torch.no_grad():
            logits = loaded.model(
                torch.from_numpy(image).float().to(loaded.device),
                torch.from_numpy(vector).float().to(loaded.device),
            ).reshape(len(image), -1)
            chunks.append(torch.softmax(logits.float(), dim=1).cpu().numpy())
    return adjust_type_probabilities(
        np.concatenate(chunks), loaded.class_names, loaded.type_adjustment, loaded.type_strength
    )


def decide_region(
    region: Region, row: np.ndarray, class_names: tuple[str, ...], threshold: float
) -> ScoredRegion:
    """Fold the reported classes together and call the region burst or not."""
    reported: dict[str, float] = {}
    for name, value in zip(class_names, row):
        target = REPORTED_AS.get(name, name)
        reported[target] = reported.get(target, 0.0) + float(value)
    non_burst = sum(float(v) for n, v in zip(class_names, row) if n in NON_BURST_CLASSES)
    evidence = float(np.clip(1.0 - non_burst, 0.0, 1.0))

    scored = ScoredRegion(
        region=region, probabilities=reported, burst_evidence=evidence,
        is_burst=evidence >= threshold,
    )
    if scored.is_burst:
        types = [name for name in reported if name not in NON_BURST_CLASSES]
        best = max(types, key=lambda name: reported[name])
        scored.burst_type = best
        scored.type_confidence = float(reported[best] / max(evidence, 1e-9))
    return scored


def score_spectrum(
    loaded: LoadedModel, spectrum: np.ndarray, metadata: dict[str, Any]
) -> list[ScoredRegion]:
    """Every candidate region of one raw spectrum, with its verdict."""
    normalized = normalize_full_spectrum(spectrum, loaded.preprocessing)
    quiet = (
        quiet_normalized_spectrum(spectrum, loaded.preprocessing)
        if "quiet_context" in loaded.views
        else None
    )
    finder = loaded.finder
    regions = find_candidate_regions(
        normalized,
        threshold=resolve_threshold(normalized, finder["threshold"], finder["adaptive"]),
        min_area=finder["min_area"],
        max_candidates=finder["max_regions"],
        hysteresis=finder["hysteresis"],
    )
    probabilities = region_probabilities(
        loaded, normalized, quiet, metadata["axes"], metadata.get("rfi_channels_mhz"), regions
    )
    return [
        decide_region(region, row, loaded.class_names, loaded.threshold)
        for region, row in zip(regions, probabilities)
    ]


def build_record(
    loaded: LoadedModel,
    scored: list[ScoredRegion],
    axes: SpectrumAxes,
    filename: str,
) -> dict[str, Any]:
    """The prediction record the rest of the backend stores and serves.

    {file_name, file_path, predicted_label, burst_probability, decision_threshold,
     confidence, alert_level, model_id, model_name}
    plus, for a burst file: {burst_type, type_confidence, type_model_id,
    type_probabilities, type_regions}.
    """
    bursts = [s for s in scored if s.is_burst]
    probability = max((s.burst_evidence for s in scored), default=0.0)
    predicted_label = "Burst" if bursts else "No_Burst"
    record: dict[str, Any] = {
        "file_name": Path(filename).name,
        "file_path": filename,
        "predicted_label": predicted_label,
        "burst_probability": probability,
        "decision_threshold": loaded.threshold,
        "confidence": probability if bursts else 1.0 - probability,
        "alert_level": relative_alert_level(probability, loaded.threshold),
        "model_id": loaded.spec.id,
        "model_name": loaded.spec.name,
    }
    if not bursts:
        return record

    # The file's type is its largest burst region's: a big region is more likely
    # the actual event, a small bright speck more likely something the model had
    # to put in some class. Regions come from the finder largest first.
    chosen = max(bursts, key=lambda s: s.region.area)
    record["burst_type"] = chosen.burst_type
    record["type_confidence"] = chosen.type_confidence
    record["type_probabilities"] = chosen.probabilities
    record["type_model_id"] = loaded.spec.id
    record["type_regions"] = [
        {
            **region_to_axes(s.region, axes),
            "burst_type": s.burst_type,
            "confidence": s.type_confidence,
        }
        for s in bursts
    ]
    return record


def predict_spectrum(
    spectrum: np.ndarray,
    metadata: dict[str, Any],
    filename: str,
    *,
    model_id: str | None = None,
) -> dict[str, Any] | None:
    """Score one read spectrum; None when the model is unavailable or scoring fails."""
    from app.ml.registry import resolve_model

    loaded = get_loaded(resolve_model(model_id))
    if loaded is None:
        return None
    try:
        scored = score_spectrum(loaded, spectrum, metadata)
    except Exception as exc:
        logger.warning("Inference failed for %s: %s", filename, exc)
        return None
    return build_record(loaded, scored, metadata["axes"], filename)


def predict_bytes(
    content: bytes, filename: str, *, model_id: str | None = None
) -> dict[str, Any] | None:
    """Score raw FITS bytes and return a prediction record, or None on error."""
    try:
        spectrum, metadata = read_spectrum_bytes(content, filename)
    except Exception as exc:
        logger.warning("Preprocessing failed for %s: %s", filename, exc)
        return None
    return predict_spectrum(spectrum, metadata, filename, model_id=model_id)
