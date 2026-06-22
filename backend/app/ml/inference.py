"""In-process burst classifier — loads the model once and scores FITS bytes.

This replaces the separate microservice (serve.py on :9000). The model is
loaded lazily on first use (or eagerly at startup via ``warm_up()``) and then
kept in memory for the lifetime of the backend process.

Fallback config for the v2_resnet18 checkpoint — the checkpoint stores the
full training config inside itself (``checkpoint["config"]``), so this is only
used when the checkpoint was saved without that field.
"""
from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Any

import numpy as np

from app.ml.metadata_features import NUM_NUMERIC, row_to_meta_vector
from app.ml.preprocessing import preprocess_bytes

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

# Module-level model state — shared across all requests.
_STATE: dict[str, Any] = {
    "model": None,
    "model_config": None,
    "device": None,
    "threshold": 0.595,
}
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


def _is_lfs_pointer(path: Path) -> bool:
    try:
        if path.stat().st_size > 1024:  # real checkpoints are ~128 MB
            return False
        with open(path, "rb") as fh:
            return fh.read(len(_LFS_POINTER_MAGIC)) == _LFS_POINTER_MAGIC
    except OSError:
        return False


def _load_model(checkpoint_path: str | Path) -> None:
    """Load (or reload) the model from a checkpoint file into _STATE."""
    from app.ml.model import create_model

    import torch

    device = _resolve_device()
    checkpoint = _torch_load(checkpoint_path, device)
    model_config = checkpoint.get("config", _FALLBACK_CONFIG)
    cfg = model_config["model"]
    vocab = cfg.get("station_vocab", {})

    model = create_model(
        cfg["name"],
        in_channels=int(cfg.get("in_channels", 1)),
        dropout=float(cfg.get("dropout", 0.25)),
        use_metadata=bool(cfg.get("use_metadata", True)),
        num_stations=len(vocab) + 1,
        num_numeric=NUM_NUMERIC,
        station_emb_dim=int(cfg.get("station_emb_dim", 8)),
    ).to(device)
    model.load_state_dict(checkpoint["model_state"])
    model.eval()

    threshold = float(model_config.get("training", {}).get("threshold", 0.595))
    _STATE.update(model=model, model_config=model_config, device=device, threshold=threshold)
    logger.info(
        "Burst classifier loaded: %s on %s (threshold=%.4f)", cfg["name"], device, threshold
    )


# ─── Download ─────────────────────────────────────────────────────────────────

def _download_model(dest: Path) -> None:
    """Download the model checkpoint from settings.ml_model_url."""
    from app.config import settings

    url = getattr(settings, "ml_model_url", "").strip()
    if not url:
        raise RuntimeError(
            "ML model checkpoint not found. It normally ships in the repo via "
            "Git LFS — run 'git lfs install && git lfs pull'. (Alternatively set "
            "ML_MODEL_URL in .env and run 'python scripts/download_model.py'.)"
        )
    import urllib.request

    dest.parent.mkdir(parents=True, exist_ok=True)
    logger.info("Downloading burst classifier checkpoint from %s …", url)
    urllib.request.urlretrieve(url, dest)
    logger.info("Checkpoint saved to %s", dest)


# ─── Public API ───────────────────────────────────────────────────────────────

def ensure_model_loaded() -> bool:
    """Load the model if not already loaded. Returns True on success."""
    if _STATE["model"] is not None:
        return True

    from app.config import settings

    try:
        import torch  # noqa: F401
    except ImportError:
        logger.warning(
            "PyTorch not installed — burst detection disabled. "
            "Install with: pip install -e '.[ml]'"
        )
        return False

    with _LOAD_LOCK:
        if _STATE["model"] is not None:  # another thread loaded it while we waited
            return True

        path = Path(getattr(settings, "ml_model_path", "ml_model/best.pt"))
        if not path.is_absolute():
            backend_root = Path(__file__).resolve().parent.parent.parent
            path = backend_root / path

        # File present but it's still a Git LFS pointer (cloned without LFS).
        if path.exists() and _is_lfs_pointer(path):
            logger.warning(
                "Model checkpoint at %s is a Git LFS pointer, not the real file. "
                "Run 'git lfs install && git lfs pull' to fetch it — "
                "burst detection is disabled until then.",
                path,
            )
            return False

        if not path.exists():
            auto_dl = getattr(settings, "ml_model_auto_download", True)
            if not auto_dl:
                logger.warning("Model checkpoint not found at %s — burst detection disabled.", path)
                return False
            try:
                _download_model(path)
            except Exception as exc:
                logger.error("Failed to download model checkpoint: %s", exc)
                return False

        try:
            _load_model(path)
            return True
        except Exception as exc:
            logger.error("Failed to load burst classifier: %s", exc)
            return False


def warm_up() -> None:
    """Eagerly load the model at startup (non-fatal — logs on failure)."""
    ensure_model_loaded()


def probability_to_alert_level(probability: float) -> str:
    if probability < 0.50:
        return "No alert"
    if probability < 0.80:
        return "Possible burst"
    if probability < 0.90:
        return "Likely burst"
    return "High-confidence burst"


def predict_bytes(content: bytes, filename: str) -> dict[str, Any] | None:
    """Score raw FITS bytes and return a prediction record, or None on error.

    The record matches the shape the rest of the backend expects:
    {file_name, file_path, predicted_label, burst_probability,
     decision_threshold, confidence, alert_level}
    """
    if not ensure_model_loaded():
        return None

    import torch

    model = _STATE["model"]
    model_config = _STATE["model_config"]
    device = _STATE["device"]
    threshold = _STATE["threshold"]

    try:
        tensor, metadata = preprocess_bytes(content, filename, model_config)
    except Exception as exc:
        logger.warning("Preprocessing failed for %s: %s", filename, exc)
        return None

    vocab = model_config.get("model", {}).get("station_vocab", {})
    use_metadata = bool(model_config.get("model", {}).get("use_metadata", True))
    meta_vec = row_to_meta_vector(metadata, vocab) if use_metadata else None

    try:
        with _PREDICT_LOCK:
            img = torch.from_numpy(tensor.astype(np.float32)).unsqueeze(0).to(device)
            inputs = [img]
            if meta_vec is not None:
                meta_t = (
                    torch.from_numpy(np.asarray(meta_vec, dtype=np.float32))
                    .unsqueeze(0)
                    .to(device)
                )
                inputs.append(meta_t)
            with torch.no_grad():
                logits = model(*inputs).reshape(-1)
                probability = float(torch.sigmoid(logits).cpu().item())
    except Exception as exc:
        logger.warning("Inference failed for %s: %s", filename, exc)
        return None

    predicted_label = "Burst" if probability >= threshold else "No_Burst"
    confidence = probability if predicted_label == "Burst" else 1.0 - probability
    return {
        "file_name": Path(filename).name,
        "file_path": filename,
        "predicted_label": predicted_label,
        "burst_probability": probability,
        "decision_threshold": threshold,
        "confidence": confidence,
        "alert_level": probability_to_alert_level(probability),
    }
