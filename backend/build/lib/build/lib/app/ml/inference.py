"""In-process burst classifiers — load each model once and score FITS bytes.

This replaces the separate microservice (serve.py on :9000). Models are loaded
lazily on first use (or eagerly at startup via ``warm_up()``) and then kept in
memory, one entry per model id, for the lifetime of the backend process.
:mod:`app.ml.registry` owns which ids exist and where their checkpoints live.

Two stages:

1. **Binary** (CCM v1.0.0 / v1.1.0) — whole-file burst / no-burst, from a
   metadata-conditioned ResNet-18. This is the gate: it decides *whether* the
   segment contains a burst.
2. **Burst type** (CCMT v1.0.0), optional — only for files stage 1 called
   ``Burst``. Bright regions are proposed from the normalized spectrum and each
   is classified into Type II / Type III / Other. CCMT was trained on crops
   around single bursts and has no background class, so it never sees a whole
   file and never runs without the binary gate.

Fallback config below is for the original v2_resnet18 checkpoint — checkpoints
normally store the full training config inside themselves
(``checkpoint["config"]``), so it is only used when that field is absent.
"""
from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from app.ml.metadata_features import NUM_NUMERIC, row_to_meta_vector
from app.ml.preprocessing import (
    crop_from_normalized,
    read_and_normalize_bytes,
    target_shape_of,
    whole_file_box,
)
from app.ml.registry import ModelSpec

logger = logging.getLogger(__name__)

# Fallback config — normally overridden by whatever is stored in the checkpoint.
_FALLBACK_CONFIG: dict[str, Any] = {
    "data": {"target_shape": [224, 224]},
    "preprocessing": {
        "background_method": "plotutil_median_db",
        "normalization": "db_window",
        "db_vmin": -1.0,
        "db_vmax": 8.0,
    },
    "model": {
        "name": "resnet18",
        "in_channels": 1,
        "dropout": 0.25,
        "use_metadata": True,
        "station_vocab": {},
        "station_emb_dim": 8,
    },
    "training": {"threshold": 0.595},
}


@dataclass
class LoadedModel:
    """One loaded checkpoint plus everything scoring needs from its config."""

    spec: ModelSpec
    model: Any
    config: dict[str, Any]
    device: Any
    threshold: float
    class_names: tuple[str, ...]
    uses_metadata: bool
    station_vocab: dict[str, int] = field(default_factory=dict)
    target_shape: tuple[int, int] = (224, 224)
    crop_margin: float = 0.0
    crop_min_rows: int = 1
    crop_min_cols: int = 1


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


def _class_names(config: dict[str, Any], spec: ModelSpec) -> tuple[str, ...]:
    """Class names ordered by label id, from the checkpoint when it has them."""
    classes = (config.get("data", {}) or {}).get("classes") or {}
    if classes:
        return tuple(name for name, _ in sorted(classes.items(), key=lambda kv: int(kv[1])))
    return spec.classes


def _crop_settings(config: dict[str, Any]) -> tuple[float, int, int]:
    crops = config.get("crops", {}) or {}
    return (
        float(crops.get("context_margin", 0.0)),
        int(crops.get("min_rows", 1)),
        int(crops.get("min_cols", 1)),
    )


def _build(spec: ModelSpec, config: dict[str, Any]) -> tuple[Any, bool, dict[str, int]]:
    """Instantiate the architecture described by a checkpoint's config."""
    cfg = config["model"]
    num_classes = int(cfg.get("num_classes", 1) or 1)

    if spec.kind == "type" or num_classes > 1:
        from app.ml.model import create_type_model

        model = create_type_model(
            cfg["name"],
            in_channels=int(cfg.get("in_channels", 1)),
            dropout=float(cfg.get("dropout", 0.25)),
            num_classes=num_classes,
        )
        return model, False, {}

    from app.ml.model import create_model

    vocab = cfg.get("station_vocab", {}) or {}
    uses_metadata = bool(cfg.get("use_metadata", True))
    model = create_model(
        cfg["name"],
        in_channels=int(cfg.get("in_channels", 1)),
        dropout=float(cfg.get("dropout", 0.25)),
        use_metadata=uses_metadata,
        num_stations=len(vocab) + 1,
        num_numeric=NUM_NUMERIC,
        station_emb_dim=int(cfg.get("station_emb_dim", 8)),
    )
    return model, uses_metadata, vocab


def _load(spec: ModelSpec, checkpoint_path: Path) -> LoadedModel:
    """Load a checkpoint into a :class:`LoadedModel` (no caching)."""
    device = _resolve_device()
    checkpoint = _torch_load(checkpoint_path, device)
    config = checkpoint.get("config", _FALLBACK_CONFIG)

    model, uses_metadata, vocab = _build(spec, config)
    model.to(device)
    model.load_state_dict(checkpoint["model_state"])
    model.eval()

    default_threshold = float(spec.metrics.get("threshold", 0.5))
    threshold = float((config.get("training", {}) or {}).get("threshold", default_threshold))
    if spec.kind == "binary" and abs(threshold - default_threshold) > 1e-6:
        # The registry publishes a threshold for the UI and for gating before the
        # model is loaded; a mismatch means one of the two is stale.
        logger.warning(
            "%s: checkpoint threshold %.4f differs from the registry's %.4f — "
            "using the checkpoint's",
            spec.name, threshold, default_threshold,
        )
    margin, min_rows, min_cols = _crop_settings(config)
    loaded = LoadedModel(
        spec=spec,
        model=model,
        config=config,
        device=device,
        threshold=threshold,
        class_names=_class_names(config, spec),
        uses_metadata=uses_metadata,
        station_vocab=vocab,
        target_shape=target_shape_of(config),
        crop_margin=margin,
        crop_min_rows=min_rows,
        crop_min_cols=min_cols,
    )
    logger.info(
        "%s loaded: %s on %s (threshold=%.4f, classes=%s)",
        spec.name, config["model"]["name"], device, threshold,
        ", ".join(loaded.class_names) or "n/a",
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
    """Load a binary model (the configured default unless given). True on success."""
    from app.ml.registry import resolve_binary

    return get_loaded(resolve_binary(model_id)) is not None


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
    """Eagerly load the models the scanner will use (non-fatal — logs on failure)."""
    from app.ml.registry import classify_types_default, resolve_binary, resolve_type

    get_loaded(resolve_binary())
    if classify_types_default():
        get_loaded(resolve_type())


def probability_to_alert_level(probability: float) -> str:
    if probability < 0.50:
        return "No alert"
    if probability < 0.80:
        return "Possible burst"
    if probability < 0.90:
        return "Likely burst"
    return "High-confidence burst"


# ─── Scoring ──────────────────────────────────────────────────────────────────


def _score_binary(
    loaded: LoadedModel, normalized: np.ndarray, metadata: dict[str, Any]
) -> float:
    """Whole-file burst probability, matching how the binary models were trained."""
    import torch

    tensor = crop_from_normalized(
        normalized, whole_file_box(normalized.shape), loaded.target_shape
    )
    meta_vec = (
        row_to_meta_vector(metadata, loaded.station_vocab) if loaded.uses_metadata else None
    )

    with _PREDICT_LOCK:
        inputs = [torch.from_numpy(tensor).unsqueeze(0).to(loaded.device)]
        if meta_vec is not None:
            inputs.append(
                torch.from_numpy(np.asarray(meta_vec, dtype=np.float32))
                .unsqueeze(0)
                .to(loaded.device)
            )
        with torch.no_grad():
            logits = loaded.model(*inputs).reshape(-1)
            return float(torch.sigmoid(logits).cpu().item())


def _classify_crop(loaded: LoadedModel, tensor: np.ndarray) -> tuple[str, float, dict[str, float]]:
    """Type one crop: returns (class name, its probability, all probabilities)."""
    import torch

    with _PREDICT_LOCK:
        image = torch.from_numpy(tensor).unsqueeze(0).to(loaded.device)
        with torch.no_grad():
            logits = loaded.model(image).reshape(1, -1)
            values = torch.softmax(logits, dim=1)[0].cpu().numpy()

    best = int(values.argmax())
    names = loaded.class_names
    name = names[best] if best < len(names) else str(best)
    return name, float(values[best]), {n: float(values[i]) for i, n in enumerate(names)}


def _typed_regions(
    loaded: LoadedModel, normalized: np.ndarray, metadata: dict[str, Any]
) -> list[Any]:
    """Propose bright regions and classify each one's burst type."""
    from app.config import settings
    from app.ml.regions import find_candidate_regions, resolve_threshold

    regions = find_candidate_regions(
        normalized,
        threshold=resolve_threshold(normalized, settings.radio_burst_region_threshold),
        min_area=settings.radio_burst_region_min_area,
        max_candidates=settings.radio_burst_region_max,
        min_rows=settings.radio_burst_region_min_rows,
        min_cols=settings.radio_burst_region_min_cols,
    )
    for region in regions:
        try:
            tensor = crop_from_normalized(
                normalized,
                region.as_box(),
                loaded.target_shape,
                context_margin=loaded.crop_margin,
                min_rows=loaded.crop_min_rows,
                min_cols=loaded.crop_min_cols,
            )
        except ValueError:
            continue
        region.burst_type, region.confidence, region.probabilities = _classify_crop(
            loaded, tensor
        )
    return regions


# One e-CALLISTO segment is ~15 minutes; used to express region time extents.
_SEGMENT_SECONDS = 15 * 60


def predict_bytes(
    content: bytes,
    filename: str,
    *,
    model_id: str | None = None,
    classify_types: bool | None = None,
) -> dict[str, Any] | None:
    """Score raw FITS bytes and return a prediction record, or None on error.

    The record keeps the shape the rest of the backend expects and only *adds*
    fields, so callers that ignore the new ones keep working:
    {file_name, file_path, predicted_label, burst_probability,
     decision_threshold, confidence, alert_level, model_id, model_name}
    plus, when the burst-type stage ran on a burst:
    {burst_type, type_confidence, type_model_id, type_probabilities, type_regions}
    """
    from app.ml.registry import classify_types_default, resolve_binary, resolve_type

    binary = get_loaded(resolve_binary(model_id))
    if binary is None:
        return None

    try:
        normalized, metadata = read_and_normalize_bytes(
            content, filename, binary.config, freq_source=binary.spec.freq_source
        )
    except Exception as exc:
        logger.warning("Preprocessing failed for %s: %s", filename, exc)
        return None

    try:
        probability = _score_binary(binary, normalized, metadata)
    except Exception as exc:
        logger.warning("Inference failed for %s: %s", filename, exc)
        return None

    predicted_label = "Burst" if probability >= binary.threshold else "No_Burst"
    confidence = probability if predicted_label == "Burst" else 1.0 - probability
    record: dict[str, Any] = {
        "file_name": Path(filename).name,
        "file_path": filename,
        "predicted_label": predicted_label,
        "burst_probability": probability,
        "decision_threshold": binary.threshold,
        "confidence": confidence,
        "alert_level": probability_to_alert_level(probability),
        "model_id": binary.spec.id,
        "model_name": binary.spec.name,
    }

    # Stage 2: type the burst. Gated on the binary verdict — the region finder is
    # a brightness heuristic that would happily "type" RFI in a quiet file.
    wants_types = classify_types_default() if classify_types is None else bool(classify_types)
    if not (wants_types and predicted_label == "Burst"):
        return record

    type_model = get_loaded(resolve_type())
    if type_model is None:
        return record

    try:
        from app.ml.regions import dominant_type, region_to_axes

        regions = _typed_regions(type_model, normalized, metadata)
    except Exception as exc:
        # Typing is additive: a failure here must not lose the binary result.
        logger.warning("Burst typing failed for %s: %s", filename, exc)
        return record

    best = dominant_type(regions)
    record["type_model_id"] = type_model.spec.id
    record["burst_type"] = best
    record["type_regions"] = [
        region_to_axes(r, metadata, _SEGMENT_SECONDS) for r in regions if r.burst_type
    ]
    if best is not None:
        chosen = max((r for r in regions if r.burst_type == best), key=lambda r: r.area)
        record["type_confidence"] = chosen.confidence
        record["type_probabilities"] = chosen.probabilities
    return record
