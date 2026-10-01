"""In-process BnB v1.0 burst model — load it once and score FITS bytes.

Models are loaded lazily on first use (or eagerly at startup via ``warm_up()``)
and then kept in memory, one entry per model id, for the lifetime of the backend
process. :mod:`app.ml.registry` owns which ids exist and where their checkpoints
live.

## How a file is scored

BnB v1.0 was trained on whole files, so scoring mirrors the CALLISTO Trainer's
binary stage (``CascadePredictor._score_binary``) step for step:

1. the whole spectrum is normalized and resized to 224x224
   (:mod:`app.ml.preprocessing`);
2. its station, frequency range and date become the metadata vector
   (:mod:`app.ml.metadata_features`);
3. the network gives one burst probability, and the file is a burst when it
   reaches the threshold tuned on the validation split.

The model does not type bursts, so a record never carries a burst type.
"""
from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from app.ml.metadata_features import NUM_NUMERIC, meta_vector
from app.ml.preprocessing import normalize_full_spectrum, read_spectrum_bytes, whole_file_tensor
from app.ml.registry import ModelSpec

logger = logging.getLogger(__name__)

NO_BURST = "No_Burst"
BURST = "Burst"


@dataclass
class LoadedModel:
    """One loaded checkpoint plus everything scoring needs from its config."""

    spec: ModelSpec
    model: Any
    config: dict[str, Any]
    device: Any
    # Decision threshold on the burst probability.
    threshold: float
    preprocessing: dict[str, Any]
    target_shape: tuple[int, int]
    # Station name -> embedding index; anything else is 0.
    station_vocab: dict[str, int]


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


def _load(spec: ModelSpec, checkpoint_path: Path) -> LoadedModel:
    """Load a checkpoint into a :class:`LoadedModel` (no caching)."""
    from app.ml.model import build_model

    device = _resolve_device()
    checkpoint = _torch_load(checkpoint_path, device)
    config = checkpoint["config"]
    model_cfg = config["model"]

    class_names = _class_names(config)
    if class_names != (NO_BURST, BURST):
        raise ValueError(f"not a binary burst model: its classes are {list(class_names)}")

    model = build_model(model_cfg, num_numeric=NUM_NUMERIC)
    model.load_state_dict(checkpoint["model_state"])
    model.to(device)
    model.eval()

    published = float(spec.metrics.get("threshold", 0.5))
    tuned = (config.get("training", {}) or {}).get("threshold")
    if tuned is None:
        logger.warning(
            "%s: checkpoint has no tuned threshold — using the registry's %.4f",
            spec.name, published,
        )
        threshold = published
    else:
        threshold = float(tuned)
        if abs(threshold - published) > 1e-6:
            # The registry publishes the threshold for the UI and for gating
            # before the model is loaded; a mismatch means one of them is stale.
            logger.warning(
                "%s: checkpoint threshold %.4f differs from the registry's %.4f — "
                "using the checkpoint's",
                spec.name, threshold, published,
            )

    target = (config.get("data", {}) or {}).get("target_shape") or (224, 224)
    loaded = LoadedModel(
        spec=spec,
        model=model,
        config=config,
        device=device,
        threshold=threshold,
        preprocessing=config["preprocessing"],
        target_shape=(int(target[0]), int(target[1])),
        station_vocab={str(k): int(v) for k, v in (model_cfg.get("station_vocab") or {}).items()},
    )
    logger.info(
        "%s loaded on %s (threshold=%.4f, backbone=%s, %d known stations)",
        spec.name, device, threshold, model_cfg.get("name"), len(loaded.station_vocab),
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
            "classes": [NO_BURST, BURST],
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

    With a threshold away from 0.5, a probability between the two would read
    "Possible burst" on the fixed bands while the verdict beside it says
    No_Burst (or the reverse). So the probability is rescaled for the bands,
    mapping the threshold to 0.5.
    """
    if threshold is None or not 0.0 < threshold < 1.0:
        return probability_to_alert_level(probability)
    if probability >= threshold:
        scaled = 0.5 + 0.5 * (probability - threshold) / (1.0 - threshold)
    else:
        scaled = 0.5 * probability / threshold
    return probability_to_alert_level(float(scaled))


# ─── Scoring ──────────────────────────────────────────────────────────────────


def model_inputs(
    loaded: LoadedModel, spectrum: np.ndarray, metadata: dict[str, Any]
) -> tuple[np.ndarray, np.ndarray]:
    """The ``[1, H, W]`` image and the metadata vector for one file (no torch)."""
    normalized = normalize_full_spectrum(spectrum, loaded.preprocessing)
    image = whole_file_tensor(normalized, loaded.target_shape)
    return image, meta_vector(metadata, loaded.station_vocab)


def score_spectrum(loaded: LoadedModel, spectrum: np.ndarray, metadata: dict[str, Any]) -> float:
    """The file's burst probability."""
    import torch

    image, meta = model_inputs(loaded, spectrum, metadata)
    image_t = torch.from_numpy(image[np.newaxis]).float().to(loaded.device)
    meta_t = torch.from_numpy(meta[np.newaxis]).float().to(loaded.device)
    with _PREDICT_LOCK, torch.no_grad():
        logit = loaded.model(image_t, meta_t).reshape(-1)
        return float(torch.sigmoid(logit)[0].item())


def build_record(loaded: LoadedModel, probability: float, filename: str) -> dict[str, Any]:
    """The prediction record the rest of the backend stores and serves.

    {file_name, file_path, predicted_label, burst_probability, decision_threshold,
     confidence, alert_level, model_id, model_name}
    """
    is_burst = probability >= loaded.threshold
    return {
        "file_name": Path(filename).name,
        "file_path": filename,
        "predicted_label": BURST if is_burst else NO_BURST,
        "burst_probability": probability,
        "decision_threshold": loaded.threshold,
        "confidence": probability if is_burst else 1.0 - probability,
        "alert_level": relative_alert_level(probability, loaded.threshold),
        "model_id": loaded.spec.id,
        "model_name": loaded.spec.name,
    }


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
        probability = score_spectrum(loaded, spectrum, metadata)
    except Exception as exc:
        logger.warning("Inference failed for %s: %s", filename, exc)
        return None
    return build_record(loaded, probability, filename)


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
