"""Which burst model the automatic detection uses — read it, change it.

The automatic radio-burst scan runs **one** model at a time (see
``app/services/radio_burst_service.py``); this module owns that choice end to
end. It describes the selectable models for the UI, validates and persists a
new choice into ``app_settings``, applies it to the in-process registry so the
running scheduler picks it up on its next pass, and re-applies the stored choice
on startup.

Why not leave it to ``RADIO_BURST_MODEL``: the model is an operational
choice made by whoever is watching the Sun, from the Settings page, and it has
to take effect on a running backend — not require a .env edit and a restart.
The env var stays the default for a fresh deployment; a saved selection wins.

Switching models is safe by construction: detections are deduped per model
(``processed_filenames_since(..., model_id=...)``), so the next scan re-scores
the recent window with the new model instead of skipping it, the backfill
re-scores older days (its coverage is per model too), and events are re-derived
from those detections with each model's own alert threshold.
"""
from __future__ import annotations

import asyncio
import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.ml import registry
from app.ml.registry import ModelSpec
from app.repositories.app_settings_repo import get_or_create_settings, save_settings
from app.schemas.radio_schema import ModelInfo, ModelsResponse

logger = logging.getLogger(__name__)


class ModelUnavailableError(Exception):
    """Raised when a model exists but its checkpoint is not usable on this box."""


# ── Describe ─────────────────────────────────────────────────────────────────


def describe_models() -> ModelsResponse:
    """Every registered model plus the active defaults, as the UI sees them.

    ``available`` reflects whether each checkpoint is actually on disk (and not
    an unpulled Git LFS pointer), so the UI can disable a model up front rather
    than surfacing a mid-scan failure.
    """
    active = registry.resolve_model()
    models = [
        ModelInfo(
            id=spec.id,
            name=spec.name,
            full_name=spec.full_name,
            kind=spec.kind,
            version=spec.version,
            description=spec.description,
            available=registry.is_available(spec),
            threshold=spec.metrics.get("threshold"),
            classes=list(spec.classes),
            metrics=dict(spec.metrics),
            is_default=spec.id == active.id,
        )
        for spec in registry.list_specs()
    ]
    return ModelsResponse(
        models=models,
        default_model=active.id,
        default_model_source="selected" if registry.model_selection() else "config",
    )


# ── Select ───────────────────────────────────────────────────────────────────


def _warm_up(spec: ModelSpec) -> None:
    """Load the newly selected checkpoint in the background.

    Best-effort: the scan loads on first use anyway, this only spares the next
    pass a cold start. A failure here is already logged by the loader.
    """
    from app.ml.inference import ensure_model_loaded

    async def _run() -> None:
        try:
            await asyncio.to_thread(ensure_model_loaded, spec.id)
        except Exception as exc:  # noqa: BLE001 - warm-up must never surface
            logger.warning("warm-up of %s failed: %s", spec.name, exc)

    try:
        asyncio.get_running_loop().create_task(_run())
    except RuntimeError:  # no loop (sync caller) — skip; first use will load it
        pass


async def select_model(db: AsyncSession, model_id: str) -> ModelsResponse:
    """Make ``model_id`` the model the automatic scan runs, and persist it.

    Raises ``registry.UnknownModelError`` for an unknown id, and
    ``ModelUnavailableError`` when its checkpoint is missing — picking a model
    that cannot load would quietly stop burst detection, which is exactly the
    failure this selector exists to avoid.
    """
    spec = registry.get_spec((model_id or "").strip())
    if not registry.is_available(spec):
        raise ModelUnavailableError(
            f"{spec.name}'s checkpoint is missing or is an unpulled Git LFS "
            f"pointer — run 'git lfs install && git lfs pull' in the repo, then "
            f"select it again."
        )

    await save_settings(db, {"radio_burst_binary_model": spec.id})
    registry.set_model_selection(spec.id)
    logger.info("automatic burst detection now uses %s", spec.name)
    _warm_up(spec)
    return describe_models()


async def load_saved_model(db: AsyncSession) -> ModelSpec | None:
    """Re-apply the saved selection on startup. Returns the spec, or None.

    A stored id the registry no longer knows (a model retired between releases)
    is cleared, leaving the configured default in charge rather than failing
    startup — and rather than warning about the same stale id on every start.
    """
    row = await get_or_create_settings(db)
    saved = (row.radio_burst_binary_model or "").strip()
    if not saved:
        return None
    try:
        spec = registry.set_model_selection(saved)
    except registry.UnknownModelError:
        logger.info(
            "saved burst model '%s' has been retired — using %s",
            saved, registry.resolve_model().name,
        )
        await save_settings(db, {"radio_burst_binary_model": ""})
        return None
    if spec is not None:
        logger.info("automatic burst detection uses the saved model %s", spec.name)
    return spec
