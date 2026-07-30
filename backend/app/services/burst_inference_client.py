"""In-process burst classifier client — replaces the HTTP microservice.

The model runs natively inside the dashboard backend (no separate port 9000
service). Inference is blocking (PyTorch forward pass); it runs in a thread
pool via asyncio.to_thread so the event loop is never blocked.

The rest of the backend (radio_burst_service, burst_predictor_service) calls
predict_url(), optionally naming which model to score with — see
app/ml/registry.py for the available ids.
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


async def predict_url(
    url: str,
    filename: str | None = None,
    *,
    model_id: str | None = None,
    classify_types: bool | None = None,
) -> dict[str, Any] | None:
    """Download the .fit.gz at ``url`` and return the in-process prediction.

    ``model_id`` selects the binary classifier (None = the configured default)
    and ``classify_types`` toggles the burst-type stage (None = the configured
    default). Returns the prediction record dict or None if download or
    inference failed.
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
    from functools import partial

    try:
        # Run the blocking torch forward pass off the event loop.
        record = await asyncio.to_thread(
            partial(
                predict_bytes,
                content,
                name,
                model_id=model_id,
                classify_types=classify_types,
            )
        )
    except Exception as exc:
        logger.warning("burst inference: scoring failed for %s: %s", name, exc)
        return None

    return record


async def health() -> dict[str, Any]:
    """Return a health-like dict matching the old microservice /healthz shape."""
    from app.ml.inference import model_state
    from app.ml.registry import resolve_binary

    try:
        import torch  # noqa: F401
        torch_ok = True
    except ImportError:
        torch_ok = False

    loaded = model_state()
    active = resolve_binary().id
    active_state = loaded.get(active)
    return {
        "status": "ok" if active_state else ("unavailable" if not torch_ok else "loading"),
        "model_loaded": active_state is not None,
        "active_model": active,
        "device": active_state["device"] if active_state else None,
        "threshold": active_state["threshold"] if active_state else None,
        "models": loaded,
        "backend": "native",
    }
