"""Client for the ML burst-classifier microservice.

The trained model runs in a separate service (the Burst Identifier project) so
the backend needs neither PyTorch nor the 129 MB checkpoint. This module is a
thin async wrapper over its HTTP API; the service is stateless and scores one
e-CALLISTO ``.fit.gz`` file (given by URL) per call.
"""
from __future__ import annotations

import logging
from typing import Any

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

# Generous timeout: the service downloads the FITS, preprocesses, and runs a
# forward pass. Downloads from the e-CALLISTO archive dominate.
_TIMEOUT = httpx.Timeout(90.0)


async def predict_url(url: str, filename: str | None = None) -> dict[str, Any] | None:
    """Score the file at ``url``; returns the prediction record or None on error.

    The record matches the service's ``_prediction_record`` shape:
    ``{file_name, file_path, predicted_label, burst_probability,
    decision_threshold, confidence, alert_level}``.
    """
    endpoint = f"{settings.ml_inference_url.rstrip('/')}/predict"
    payload: dict[str, Any] = {"url": url}
    if filename:
        payload["filename"] = filename
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.post(endpoint, json=payload)
            resp.raise_for_status()
            return resp.json()
    except httpx.HTTPError as exc:
        logger.warning("burst inference failed for %s: %s", filename or url, exc)
        return None


async def health() -> dict[str, Any] | None:
    """Return the service's health payload, or None if unreachable."""
    endpoint = f"{settings.ml_inference_url.rstrip('/')}/healthz"
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(10.0)) as client:
            resp = await client.get(endpoint)
            resp.raise_for_status()
            return resp.json()
    except httpx.HTTPError as exc:
        logger.warning("burst inference health check failed: %s", exc)
        return None
