"""Model registry: identity, defaults, and per-model alert thresholds.

The registry is what makes model selection safe — a bad id must degrade to the
shipped model rather than disabling burst detection, and each model's alert gate
must follow *its own* tuned threshold. These are pure-Python checks: none of them
loads a checkpoint, so they run without torch.
"""
import pytest

from app.config import settings
from app.ml import registry
from app.ml.registry import UnknownModelError


def test_registry_lists_the_three_shipped_models():
    ids = {spec.id for spec in registry.list_specs()}
    assert ids == {"ccm-1.0.0", "ccm-1.1.0", "ccmt-1.0.0"}

    binary = {spec.id for spec in registry.list_specs("binary")}
    assert binary == {"ccm-1.0.0", "ccm-1.1.0"}
    assert [spec.id for spec in registry.list_specs("type")] == ["ccmt-1.0.0"]


def test_specs_carry_the_identity_the_ui_shows():
    spec = registry.get_spec("ccm-1.1.0")
    assert spec.name == "CCM v1.1.0"
    assert spec.full_name == "CALLISTO Classifier Model v1.1.0"
    assert spec.version == "1.1.0"
    assert spec.kind == "binary"
    assert spec.classes == ("No_Burst", "Burst")

    ccmt = registry.get_spec("ccmt-1.0.0")
    assert ccmt.name == "CCMT v1.0.0"
    # Label order is load-bearing: it maps softmax indices to names.
    assert ccmt.classes == ("Type II", "Type III", "Other")


def test_v100_keeps_header_frequencies_and_v110_uses_the_axes_table():
    # The FITS AXES table is what training used; CCM v1.0.0 deliberately stays on
    # the (wrong but consistent) header path so its outputs do not change.
    assert registry.get_spec("ccm-1.0.0").freq_source == "header"
    assert registry.get_spec("ccm-1.1.0").freq_source == "axes"


def test_unknown_id_raises():
    with pytest.raises(UnknownModelError):
        registry.get_spec("ccm-9.9.9")
    with pytest.raises(UnknownModelError):
        registry.resolve_binary("nope")


def test_kind_is_enforced_when_a_model_is_named_explicitly():
    # Asking for the type model as a binary model is a caller bug, not a fallback.
    with pytest.raises(UnknownModelError):
        registry.resolve_binary("ccmt-1.0.0")
    with pytest.raises(UnknownModelError):
        registry.resolve_type("ccm-1.1.0")


def test_resolve_binary_follows_configuration(monkeypatch):
    monkeypatch.setattr(settings, "radio_burst_binary_model", "ccm-1.0.0")
    assert registry.resolve_binary().id == "ccm-1.0.0"
    monkeypatch.setattr(settings, "radio_burst_binary_model", "ccm-1.1.0")
    assert registry.resolve_binary().id == "ccm-1.1.0"
    # An explicit argument always wins over configuration.
    assert registry.resolve_binary("ccm-1.0.0").id == "ccm-1.0.0"


def test_a_misconfigured_default_degrades_to_the_shipped_model(monkeypatch):
    # A typo in RADIO_BURST_BINARY_MODEL must not disable burst detection.
    monkeypatch.setattr(settings, "radio_burst_binary_model", "ccm-1.1.O")  # letter O
    assert registry.resolve_binary().id == "ccm-1.0.0"
    monkeypatch.setattr(settings, "radio_burst_binary_model", "")
    assert registry.resolve_binary().id == "ccm-1.0.0"
    # A *type* model configured as the binary default is equally invalid.
    monkeypatch.setattr(settings, "radio_burst_binary_model", "ccmt-1.0.0")
    assert registry.resolve_binary().id == "ccm-1.0.0"

    monkeypatch.setattr(settings, "radio_burst_type_model", "garbage")
    assert registry.resolve_type().id == "ccmt-1.0.0"


def test_alert_minimum_defaults_to_each_models_own_threshold(monkeypatch):
    # 0 means "use the model's threshold" — the whole reason the setting changed,
    # since a single global figure would silently drop CCM v1.1.0 detections
    # between 0.51 and CCM v1.0.0's 0.595.
    monkeypatch.setattr(settings, "radio_burst_alert_min_probability", 0.0)
    assert registry.alert_min_probability(registry.get_spec("ccm-1.0.0")) == pytest.approx(0.595)
    assert registry.alert_min_probability(registry.get_spec("ccm-1.1.0")) == pytest.approx(0.51)


def test_a_positive_alert_minimum_overrides_every_model(monkeypatch):
    monkeypatch.setattr(settings, "radio_burst_alert_min_probability", 0.8)
    for model_id in ("ccm-1.0.0", "ccm-1.1.0"):
        assert registry.alert_min_probability(registry.get_spec(model_id)) == pytest.approx(0.8)


def test_checkpoint_paths_resolve_under_the_backend_root():
    paths = {spec.id: registry.checkpoint_path(spec) for spec in registry.list_specs()}
    assert paths["ccm-1.0.0"].name == "best.pt"
    assert paths["ccm-1.1.0"].name == "ccm_v1_1_0.pt"
    assert paths["ccmt-1.0.0"].name == "ccmt_v1_0_0.pt"
    for path in paths.values():
        assert path.is_absolute()
        assert path.parent.name == "ml_model"


def test_classify_types_default_follows_configuration(monkeypatch):
    monkeypatch.setattr(settings, "radio_burst_classify_types", False)
    assert registry.classify_types_default() is False
    monkeypatch.setattr(settings, "radio_burst_classify_types", True)
    assert registry.classify_types_default() is True
