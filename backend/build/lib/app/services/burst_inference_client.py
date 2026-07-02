"""In-process burst classifier client — replaces the HTTP microservice.

The model runs natively inside the dashboard backend (no separate port 9000
service). Inference is blocking (PyTorch forward pass); it runs in a thread
pool via asyncio.to_thread so the event loop is never blocked.

The rest of the backend (radio_burst_service, burst_predictor_service) calls
predict_url() exactly as before — the HTTP-vs-native switch is transparent.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import httpx

from app.ml.inference import predict_bytes

logger = logging.getLogger(__name__)

# Download timeout: e-CALLISTO archive fetches dominate over inference time.
_DOWNLOAD_TIMEOUT = httpx.Timeout(90.0)


async def predict_url(url: str, filename: str | None = None) -> dict[str, Any] | None:
    """Download the .fit.gz at ``url`` and return the in-process prediction.

    Returns the prediction record dict (same shape as the old microservice
    response) or None if download or inference failed.
    """
    name = filename or Path(url).name or "remote.fit.gz"
    try:
        async with httpx.AsyncClient(timeout=_DOWNLOAD_TIMEOUT) as client:
            resp = await client.get(url, follow_redirects=True)
            resp.raise_for_status()
            content = resp.content
    except httpx.HTTPError as exc:
        logger.warning("burst inference: download failed for %s: %s", name, exc)
        return None

    import asyncio

    try:
        # Run the blocking torch forward pass off the event loop.
        record = await asyncio.to_thread(predict_bytes, content, name)
    except Exception as exc:
        logger.warning("burst inference: scoring failed for %s: %s", name, exc)
        return None

    return record


async def health() -> dict[str, Any]:
    """Return a health-like dict matching the old microservice /healthz shape."""
    from app.ml.inference import _STATE
    import torch

    try:
        torch_ok = True
    except ImportError:
        torch_ok = False

    device = _STATE.get("device")
    return {
        "status": "ok" if _STATE.get("model") is not None else (
            "unavailable" if not torch_ok else "loading"
        ),
        "model_loaded": _STATE.get("model") is not None,
        "device": str(device) if device is not None else None,
        "threshold": _STATE.get("threshold", 0.595),
        "backend": "native",
    }
