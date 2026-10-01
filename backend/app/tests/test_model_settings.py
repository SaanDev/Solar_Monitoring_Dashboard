"""Choosing the automatic burst-detection model from the Settings page.

The point of the feature is that the choice is *operational*: it must reach the
background scanner in this process, survive a restart, and refuse a model that
cannot actually run — a silently broken selection would stop burst alerts
entirely, which is the one failure mode a model picker must not introduce.

Only BnB v1.0 ships, so a stand-in second model is registered here to exercise
switching. Inference is never touched (no checkpoint is loaded); availability is
stubbed so the tests pass with or without the Git LFS checkpoint present.
"""
from dataclasses import replace

import pytest
from httpx import ASGITransport, AsyncClient

from app.config import settings
from app.main import app
from app.ml import registry
from app.repositories.app_settings_repo import get_or_create_settings, save_settings
from app.services import model_settings_service as mss

_SHIPPED = "bnb-1.0.0"
_OTHER = "bnb-9.0.0"


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


@pytest.fixture(autouse=True)
def isolated_selection(monkeypatch):
    """The selection is a process-global; never let one test leak into another.

    Warm-up is stubbed out too: selecting a model must not drag a real
    (torch-dependent) checkpoint into a unit test.
    """
    monkeypatch.setattr(mss, "_warm_up", lambda spec: None)
    registry.set_model_selection(None)
    yield
    registry.set_model_selection(None)


@pytest.fixture(autouse=True)
def second_model(monkeypatch):
    other = replace(
        registry.BNB_V100, id=_OTHER, name="BnB v9.0", metrics={"threshold": 0.6}
    )
    monkeypatch.setitem(registry._SPECS, _OTHER, other)
    monkeypatch.setattr(registry, "is_available", lambda spec: True)
    monkeypatch.setattr(settings, "radio_burst_model", _SHIPPED)
    monkeypatch.setattr(settings, "radio_burst_alert_min_probability", 0.0)
    return other


# ── Registry precedence ──────────────────────────────────────────────────────


def test_selection_overrides_the_configured_default():
    assert registry.resolve_model().id == _SHIPPED

    registry.set_model_selection(_OTHER)
    assert registry.model_selection() == _OTHER
    assert registry.resolve_model().id == _OTHER
    # An explicit per-run id (the Burst Detector page) still wins over both.
    assert registry.resolve_model(_SHIPPED).id == _SHIPPED

    # Clearing hands control back to configuration.
    registry.set_model_selection(None)
    assert registry.resolve_model().id == _SHIPPED


def test_an_invalid_selection_is_rejected_rather_than_applied():
    for bad in ("bnb-9.9.9", "ccm-2.0.1", "ccmt-1.0.0"):
        with pytest.raises(registry.UnknownModelError):
            registry.set_model_selection(bad)
        assert registry.model_selection() is None


# ── API ──────────────────────────────────────────────────────────────────────


async def test_models_endpoint_reports_where_the_default_came_from(client):
    body = (await client.get("/api/radio/models")).json()
    assert body["default_model"] == _SHIPPED
    assert body["default_model_source"] == "config"

    r = await client.put("/api/radio/models/default", json={"model_id": _OTHER})
    assert r.status_code == 200
    body = r.json()
    assert body["default_model"] == _OTHER
    assert body["default_model_source"] == "selected"
    # The response doubles as the refreshed model list the UI re-renders from.
    picked = {m["id"]: m for m in body["models"]}
    assert picked[_OTHER]["is_default"] is True
    assert picked[_SHIPPED]["is_default"] is False


async def test_selection_reaches_the_scanner_and_the_database(client, db_session):
    r = await client.put("/api/radio/models/default", json={"model_id": _OTHER})
    assert r.status_code == 200

    # What the automatic scan resolves, without being passed anything.
    assert registry.resolve_model().id == _OTHER
    # …and its alert gate follows that model's own threshold.
    assert registry.alert_min_probability(registry.resolve_model()) == pytest.approx(0.6)

    row = await get_or_create_settings(db_session)
    assert row.radio_burst_binary_model == _OTHER


async def test_unknown_and_retired_models_are_refused(client):
    for bad in ("bnb-9.9.9", "ccm-2.0.1"):
        r = await client.put("/api/radio/models/default", json={"model_id": bad})
        assert r.status_code == 400
    assert registry.model_selection() is None


async def test_a_model_with_no_checkpoint_cannot_be_selected(client, monkeypatch):
    # Choosing a model whose checkpoint was never pulled would stop detection
    # silently, so it fails loudly with instructions instead.
    monkeypatch.setattr(registry, "is_available", lambda spec: spec.id != _OTHER)

    r = await client.put("/api/radio/models/default", json={"model_id": _OTHER})
    assert r.status_code == 409
    assert "git lfs" in r.json()["detail"].lower()
    assert registry.model_selection() is None


# ── Persistence across restarts ──────────────────────────────────────────────


async def test_the_saved_model_is_restored_on_startup(client, db_session):
    await client.put("/api/radio/models/default", json={"model_id": _OTHER})

    registry.set_model_selection(None)  # simulate a restart: memory is empty
    assert registry.resolve_model().id == _SHIPPED

    spec = await mss.load_saved_model(db_session)
    assert spec is not None and spec.id == _OTHER
    assert registry.resolve_model().id == _OTHER


async def test_an_untouched_database_follows_configuration(db_session):
    assert await mss.load_saved_model(db_session) is None
    assert registry.resolve_model().id == _SHIPPED


async def test_a_retired_saved_model_is_cleared_on_startup(db_session):
    """An install that had picked CCM v2.0.1 moves to BnB v1.0 by itself."""
    await save_settings(db_session, {"radio_burst_binary_model": "ccm-2.0.1"})

    assert await mss.load_saved_model(db_session) is None
    assert registry.model_selection() is None
    assert registry.resolve_model().id == _SHIPPED
    # Cleared, so the next start does not trip over it again.
    assert (await get_or_create_settings(db_session)).radio_burst_binary_model == ""
