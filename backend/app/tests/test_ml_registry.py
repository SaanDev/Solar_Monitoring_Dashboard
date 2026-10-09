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

_BNB = 0.786865234375
_BNB10 = 0.5634765625
_CCM2 = 0.7975836745463312


def test_registry_ships_bnb_v1_1_only():
    assert [spec.id for spec in registry.list_specs()] == ["bnb-1.1.0"]


def test_spec_carries_the_identity_the_ui_shows():
    spec = registry.get_spec("bnb-1.1.0")
    assert spec.name == "BnB v1.1"
    assert spec.full_name == "Burst / No-Burst classifier v1.1"
    assert spec.version == "1.1.0"
    assert spec.kind == "binary"
    # It does not type bursts.
    assert spec.classes == ()
    assert spec.metrics["threshold"] == _BNB


@pytest.mark.parametrize(
    "model_id", ["ccm-9.9.9", "ccm-1.1.0", "ccm-2.0.0", "ccm-2.0.1", "ccmt-1.0.0", "bnb-1.0.0", ""]
)
def test_unknown_and_retired_ids_raise(model_id):
    with pytest.raises(UnknownModelError):
        registry.get_spec(model_id)


def test_resolve_model_follows_configuration(monkeypatch):
    monkeypatch.setattr(settings, "radio_burst_model", "bnb-1.1.0")
    assert registry.resolve_model().id == "bnb-1.1.0"
    assert registry.resolve_model("bnb-1.1.0").id == "bnb-1.1.0"


@pytest.mark.parametrize("configured", ["bnb-1.0.0", "ccm-2.0.1", "ccm-1.1.0", "not-a-model", ""])
def test_a_misconfigured_default_degrades_to_the_shipped_model(monkeypatch, configured):
    # An old .env still naming a retired model must not disable detection.
    monkeypatch.setattr(settings, "radio_burst_model", configured)
    assert registry.resolve_model() is registry.BNB_V110


def test_an_explicit_unknown_model_is_an_error(monkeypatch):
    # Unlike configuration, an explicit per-run choice deserves an error message.
    with pytest.raises(UnknownModelError):
        registry.resolve_model("ccm-2.0.0")


def test_alert_minimum_defaults_to_the_tuned_threshold(monkeypatch):
    monkeypatch.setattr(settings, "radio_burst_alert_min_probability", 0.0)
    assert registry.alert_min_probability(registry.BNB_V110) == pytest.approx(_BNB)


def test_a_positive_alert_minimum_overrides_every_model(monkeypatch):
    monkeypatch.setattr(settings, "radio_burst_alert_min_probability", 0.9)
    assert registry.alert_min_probability(registry.BNB_V110) == 0.9
    assert registry.alert_min_probability_for("ccm-2.0.1") == 0.9


def test_stored_rows_are_gated_by_the_model_that_made_them(monkeypatch):
    monkeypatch.setattr(settings, "radio_burst_alert_min_probability", 0.0)
    assert registry.alert_min_probability_for("ccm-1.0.0") == pytest.approx(0.595)
    assert registry.alert_min_probability_for("ccm-1.1.0") == pytest.approx(0.51)
    assert registry.alert_min_probability_for("ccm-2.0.0") == pytest.approx(_CCM2)
    assert registry.alert_min_probability_for("ccm-2.0.1") == pytest.approx(_CCM2)
    assert registry.alert_min_probability_for("bnb-1.0.0") == pytest.approx(_BNB10)
    assert registry.alert_min_probability_for("bnb-1.1.0") == pytest.approx(_BNB)
    # Missing or never-registered ids fall back to the active model.
    assert registry.alert_min_probability_for(None) == pytest.approx(_BNB)
    assert registry.alert_min_probability_for("ccm-0.9.0") == pytest.approx(_BNB)


def test_display_names_cover_retired_models():
    assert registry.model_display_name("bnb-1.1.0") == "BnB v1.1"
    assert registry.model_display_name("bnb-1.0.0") == "BnB v1.0"
    assert registry.model_display_name("ccm-2.0.1") == "CCM v2.0.1"
    assert registry.model_display_name("ccm-2.0.0") == "CCM v2.0"
    assert registry.model_display_name("ccm-1.1.0") == "CCM v1.1.0"
    assert registry.model_display_name("ccm-0.9.0") == "ccm-0.9.0"
    assert registry.model_display_name(None) == ""


def test_checkpoint_path_resolves_under_the_backend_root():
    path = registry.checkpoint_path(registry.BNB_V110)
    assert path.is_absolute()
    assert path.parts[-2:] == ("ml_model", "bnb_v1_1.pt")
