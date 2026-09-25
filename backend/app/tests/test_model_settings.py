"""Choosing the automatic burst-detection model from the Settings page.

The point of the feature is that the choice is *operational*: it must reach the
background scanner in this process, survive a restart, and refuse a model that
cannot actually run — a silently broken selection would stop burst alerts
entirely, which is the one failure mode a model picker must not introduce.

Inference is never touched here (no checkpoint is loaded); availability is
stubbed so the tests pass with or without the Git LFS checkpoints present.
"""
import pytest
from httpx import ASGITransport, AsyncClient

from app.config import settings
from app.main import app
from app.ml import registry
from app.repositories.app_settings_repo import get_or_create_settings
from app.services import model_settings_service as mss


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


@pytest.fixture(autouse=True)
def isolated_selection(monkeypatch):
    """The selection is a process-global; never let one test leak into another.

    Warm-up is stubbed out too: selecting a model must not drag a real
    (multi-hundred-MB, torch-dependent) checkpoint into a unit test.
    """
    monkeypatch.setattr(mss, "_warm_up", lambda spec: None)
    registry.set_binary_selection(None)
    yield
    registry.set_binary_selection(None)


@pytest.fixture(autouse=True)
def available_checkpoints(monkeypatch):
    monkeypatch.setattr(registry, "is_available", lambda spec: True)


# ── Registry precedence ──────────────────────────────────────────────────────


def test_selection_overrides_the_configured_default(monkeypatch):
    monkeypatch.setattr(settings, "radio_burst_binary_model", "ccm-1.1.0")
    assert registry.resolve_binary().id == "ccm-1.1.0"

    registry.set_binary_selection("ccm-1.0.0")
    assert registry.binary_selection() == "ccm-1.0.0"
    assert registry.resolve_binary().id == "ccm-1.0.0"
    # An explicit per-run id (the Burst Detector page) still wins over both.
    assert registry.resolve_binary("ccm-1.1.0").id == "ccm-1.1.0"

    # Clearing hands control back to configuration.
    registry.set_binary_selection(None)
    assert registry.resolve_binary().id == "ccm-1.1.0"


def test_an_invalid_selection_is_rejected_rather_than_applied():
    for bad in ("ccm-9.9.9", "ccmt-1.0.0"):
        with pytest.raises(registry.UnknownModelError):
            registry.set_binary_selection(bad)
        assert registry.binary_selection() is None


# ── API ──────────────────────────────────────────────────────────────────────


async def test_models_endpoint_reports_where_the_default_came_from(client, monkeypatch):
    monkeypatch.setattr(settings, "radio_burst_binary_model", "ccm-1.1.0")
    body = (await client.get("/api/radio/models")).json()
    assert body["default_binary"] == "ccm-1.1.0"
    assert body["default_binary_source"] == "config"

    r = await client.put("/api/radio/models/default", json={"model_id": "ccm-1.0.0"})
    assert r.status_code == 200
    body = r.json()
    assert body["default_binary"] == "ccm-1.0.0"
    assert body["default_binary_source"] == "selected"
    # The response doubles as the refreshed model list the UI re-renders from.
    picked = {m["id"]: m for m in body["models"]}
    assert picked["ccm-1.0.0"]["is_default"] is True
    assert picked["ccm-1.1.0"]["is_default"] is False


async def test_selection_reaches_the_scanner_and_the_database(client, db_session, monkeypatch):
    monkeypatch.setattr(settings, "radio_burst_binary_model", "ccm-1.1.0")

    r = await client.put("/api/radio/models/default", json={"model_id": "ccm-1.0.0"})
    assert r.status_code == 200

    # What the automatic scan resolves, without being passed anything.
    assert registry.resolve_binary().id == "ccm-1.0.0"
    # …and its alert gate follows that model's own threshold, not the other's.
    monkeypatch.setattr(settings, "radio_burst_alert_min_probability", 0.0)
    assert registry.alert_min_probability(registry.resolve_binary()) == pytest.approx(0.595)

    row = await get_or_create_settings(db_session)
    assert row.radio_burst_binary_model == "ccm-1.0.0"


async def test_unknown_and_non_binary_models_are_refused(client):
    r = await client.put("/api/radio/models/default", json={"model_id": "ccm-9.9.9"})
    assert r.status_code == 400
    # The burst-*type* model is not a detector; it cannot run the scan.
    r = await client.put("/api/radio/models/default", json={"model_id": "ccmt-1.0.0"})
    assert r.status_code == 400
    assert "not a binary model" in r.json()["detail"]
    assert registry.binary_selection() is None


async def test_a_model_with_no_checkpoint_cannot_be_selected(client, monkeypatch):
    # Choosing a model whose checkpoint was never pulled would stop detection
    # silently, so it fails loudly with instructions instead.
    monkeypatch.setattr(registry, "is_available", lambda spec: spec.id != "ccm-1.0.0")

    r = await client.put("/api/radio/models/default", json={"model_id": "ccm-1.0.0"})
    assert r.status_code == 409
    assert "git lfs" in r.json()["detail"].lower()
    assert registry.binary_selection() is None


# ── Persistence across restarts ──────────────────────────────────────────────


async def test_the_saved_model_is_restored_on_startup(client, db_session, monkeypatch):
    monkeypatch.setattr(settings, "radio_burst_binary_model", "ccm-1.1.0")
    await client.put("/api/radio/models/default", json={"model_id": "ccm-1.0.0"})

    registry.set_binary_selection(None)  # simulate a restart: memory is empty
    assert registry.resolve_binary().id == "ccm-1.1.0"

    spec = await mss.load_saved_binary_model(db_session)
    assert spec is not None and spec.id == "ccm-1.0.0"
    assert registry.resolve_binary().id == "ccm-1.0.0"


async def test_an_untouched_database_follows_configuration(db_session, monkeypatch):
    monkeypatch.setattr(settings, "radio_burst_binary_model", "ccm-1.1.0")
    assert await mss.load_saved_binary_model(db_session) is None
    assert registry.resolve_binary().id == "ccm-1.1.0"


async def test_a_retired_saved_model_does_not_break_startup(db_session):
    from app.repositories.app_settings_repo import save_settings

    await save_settings(db_session, {"radio_burst_binary_model": "ccm-0.0.1"})
    assert await mss.load_saved_binary_model(db_session) is None
    assert registry.binary_selection() is None
