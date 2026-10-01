"""The shipped checkpoint must load into the architecture the code builds.

This is the highest-value ML test: a mismatch between the builder and the saved
state dict is the most likely way this feature breaks, and it is invisible until
inference runs. ``load_state_dict`` defaults to ``strict=True``, so a load that
succeeds proves every key matched. The probabilities for the synthetic files in
:mod:`app.tests.bnb_cases` must also be the ones the CALLISTO Trainer computed,
which checks the whole path — FITS reading, normalization, metadata vector and
network — end to end.

Skipped when torch is absent (the default local venv) or the checkpoint has not
been pulled from Git LFS; it runs in the backend container, which has both.
"""
import pytest

from app.ml import registry
from app.ml.inference import get_loaded, predict_bytes
from app.tests.bnb_cases import CASES, case_bytes

pytest.importorskip("torch", reason="ML extras not installed")


@pytest.fixture(scope="module")
def loaded():
    spec = registry.BNB_V100
    if not registry.is_available(spec):
        pytest.skip(f"{spec.name} checkpoint not present (run: git lfs pull)")
    model = get_loaded(spec)
    assert model is not None, f"{spec.name} failed to load — see logs"
    return model


def test_checkpoint_loads_with_its_training_settings(loaded):
    assert loaded.config["model"]["name"] == "resnet34"
    # 38 trained stations; everything else shares slot 0.
    assert len(loaded.station_vocab) == 38
    assert loaded.station_vocab["BIR"] == 11
    assert loaded.target_shape == (224, 224)
    assert loaded.preprocessing["background_method"] == "plotutil_median_db"


def test_scoring_uses_the_tuned_threshold(loaded):
    # The registry publishes the threshold so alert gating works before a load;
    # it must agree with what the checkpoint actually contains.
    assert loaded.threshold == pytest.approx(registry.BNB_V100.metrics["threshold"], abs=1e-12)


def test_models_are_cached_not_reloaded(loaded):
    assert get_loaded(registry.BNB_V100) is loaded


@pytest.mark.parametrize("case", CASES, ids=[c["filename"] for c in CASES])
def test_probabilities_match_the_trainer(loaded, case):
    record = predict_bytes(case_bytes(case), case["filename"])
    assert record is not None
    assert record["burst_probability"] == pytest.approx(case["probability"], abs=1e-4)
    assert record["predicted_label"] == ("Burst" if case["burst"] else "No_Burst")
    assert record["model_id"] == "bnb-1.0.0"
    assert "burst_type" not in record
