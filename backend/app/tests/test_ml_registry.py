"""Model registry: identity, defaults, and per-model alert thresholds.

The registry is what makes model selection safe — a bad id must degrade to the
shipped model rather than disabling burst detection, and each detection must be
judged by the threshold of the model that made it, including rows the retired
models left in the database. These are pure-Python checks: none of them loads a
checkpoint, so they run without torch.
"""
import pytest

from app.config import settings
from app.ml import registry
from app.ml.registry import UnknownModelError


def test_registry_ships_ccm_v2_only():
    assert [spec.id for spec in registry.list_specs()] == ["ccm-2.0.0"]


def test_spec_carries_the_identity_the_ui_shows():
    spec = registry.get_spec("ccm-2.0.0")
    assert spec.name == "CCM v2.0"
    assert spec.full_name == "CALLISTO Classifier Model v2.0"
    assert spec.version == "2.0.0"
    assert spec.kind == "unified"
    # What the dashboard reports: Type IIIG is folded into Type III.
    assert spec.classes == ("Type II", "Type III", "Other")
    assert spec.metrics["threshold"] == pytest.approx(0.7975836745463312)


@pytest.mark.parametrize("model_id", ["ccm-9.9.9", "ccm-1.1.0", "ccmt-1.0.0", ""])
def test_unknown_and_retired_ids_raise(model_id):
    with pytest.raises(UnknownModelError):
        registry.get_spec(model_id)


def test_resolve_model_follows_configuration(monkeypatch):
    monkeypatch.setattr(settings, "radio_burst_model", "ccm-2.0.0")
    assert registry.resolve_model().id == "ccm-2.0.0"
    assert registry.resolve_model("ccm-2.0.0").id == "ccm-2.0.0"


@pytest.mark.parametrize("configured", ["ccm-1.1.0", "not-a-model", ""])
def test_a_misconfigured_default_degrades_to_the_shipped_model(monkeypatch, configured):
    # An old .env still naming a retired model must not disable detection.
    monkeypatch.setattr(settings, "radio_burst_model", configured)
    assert registry.resolve_model() is registry.CCM_V200


def test_an_explicit_unknown_model_is_an_error(monkeypatch):
    # Unlike configuration, an explicit per-run choice deserves an error message.
    with pytest.raises(UnknownModelError):
        registry.resolve_model("ccm-1.0.0")


def test_alert_minimum_defaults_to_the_calibrated_threshold(monkeypatch):
    monkeypatch.setattr(settings, "radio_burst_alert_min_probability", 0.0)
    assert registry.alert_min_probability(registry.CCM_V200) == pytest.approx(0.7976, abs=1e-4)


def test_a_positive_alert_minimum_overrides_every_model(monkeypatch):
    monkeypatch.setattr(settings, "radio_burst_alert_min_probability", 0.9)
    assert registry.alert_min_probability(registry.CCM_V200) == 0.9
    assert registry.alert_min_probability_for("ccm-1.1.0") == 0.9


def test_stored_rows_are_gated_by_the_model_that_made_them(monkeypatch):
    monkeypatch.setattr(settings, "radio_burst_alert_min_probability", 0.0)
    assert registry.alert_min_probability_for("ccm-1.0.0") == pytest.approx(0.595)
    assert registry.alert_min_probability_for("ccm-1.1.0") == pytest.approx(0.51)
    assert registry.alert_min_probability_for("ccm-2.0.0") == pytest.approx(0.7976, abs=1e-4)
    # Missing or never-registered ids fall back to the active model.
    assert registry.alert_min_probability_for(None) == pytest.approx(0.7976, abs=1e-4)
    assert registry.alert_min_probability_for("ccm-0.9.0") == pytest.approx(0.7976, abs=1e-4)


def test_display_names_cover_retired_models():
    assert registry.model_display_name("ccm-2.0.0") == "CCM v2.0"
    assert registry.model_display_name("ccm-1.1.0") == "CCM v1.1.0"
    assert registry.model_display_name("ccm-0.9.0") == "ccm-0.9.0"
    assert registry.model_display_name(None) == ""


def test_checkpoint_path_resolves_under_the_backend_root():
    path = registry.checkpoint_path(registry.CCM_V200)
    assert path.is_absolute()
    assert path.parts[-2:] == ("ml_model", "ccm_v2_0.pt")
