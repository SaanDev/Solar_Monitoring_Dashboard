"""Every shipped checkpoint must load into the architecture the code builds.

This is the highest-value ML test: a mismatch between the builder and the saved
state dict is the most likely way this feature breaks, and it is invisible until
inference runs. CCMT is the risky one — it was saved from a plain torchvision
ResNet-18 whose head was swapped in place (``conv1.*`` / ``fc.*``), so building it
as a feature backbone wrapped in ``nn.Sequential`` would produce ``0.*`` / ``1.*``
and fail. ``load_state_dict`` defaults to ``strict=True``, so a load that succeeds
proves every key matched.

Skipped when torch is absent (the default local venv) or a checkpoint has not been
pulled from Git LFS; it runs in the backend container, which has both.
"""
import pytest

from app.ml import registry
from app.ml.inference import get_loaded

pytest.importorskip("torch", reason="ML extras not installed")


@pytest.mark.parametrize("model_id", ["ccm-1.0.0", "ccm-1.1.0", "ccmt-1.0.0"])
def test_checkpoint_loads_strictly(model_id):
    spec = registry.get_spec(model_id)
    if not registry.is_available(spec):
        pytest.skip(f"{spec.name} checkpoint not present (run: git lfs pull)")

    loaded = get_loaded(spec)
    assert loaded is not None, f"{spec.name} failed to load — see logs"
    assert loaded.class_names == spec.classes
    # 224x224 is baked into the preprocessing constants; a checkpoint expecting
    # anything else would be silently mis-fed.
    assert loaded.target_shape == (224, 224)


def test_binary_checkpoints_carry_their_tuned_thresholds():
    # The registry publishes these so alert gating works before a model is loaded;
    # they must agree with what the checkpoints actually contain.
    for model_id, expected in (("ccm-1.0.0", 0.595), ("ccm-1.1.0", 0.51)):
        spec = registry.get_spec(model_id)
        if not registry.is_available(spec):
            pytest.skip(f"{spec.name} checkpoint not present")
        loaded = get_loaded(spec)
        assert loaded is not None
        assert loaded.threshold == pytest.approx(expected, abs=1e-6)
        assert loaded.uses_metadata is True


def test_type_checkpoint_is_image_only_with_three_classes():
    spec = registry.get_spec("ccmt-1.0.0")
    if not registry.is_available(spec):
        pytest.skip("CCMT checkpoint not present")
    loaded = get_loaded(spec)
    assert loaded is not None
    # No metadata branch: CCMT takes one tensor, so a second input would error.
    assert loaded.uses_metadata is False
    # Label order maps softmax indices to names and must not drift.
    assert loaded.class_names == ("Type II", "Type III", "Other")


def test_models_are_cached_not_reloaded():
    spec = registry.resolve_binary("ccm-1.1.0")
    if not registry.is_available(spec):
        pytest.skip("CCM v1.1.0 checkpoint not present")
    first = get_loaded(spec)
    assert first is not None
    assert get_loaded(spec) is first
