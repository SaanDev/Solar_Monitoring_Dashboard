"""The shipped checkpoint must load into the architecture the code builds.

This is the highest-value ML test: a mismatch between the builder and the saved
state dict is the most likely way this feature breaks, and it is invisible until
inference runs. ``load_state_dict`` defaults to ``strict=True``, so a load that
succeeds proves every key matched. The checkpoint also carries the settings the
model was calibrated with (burst threshold, region finder, type priors); those
must be the ones scoring uses.

Skipped when torch is absent (the default local venv) or the checkpoint has not
been pulled from Git LFS; it runs in the backend container, which has both.
"""
import io

import numpy as np
import pytest

from app.ml import registry
from app.ml.inference import get_loaded, predict_bytes

pytest.importorskip("torch", reason="ML extras not installed")


@pytest.fixture(scope="module")
def loaded():
    spec = registry.CCM_V200
    if not registry.is_available(spec):
        pytest.skip(f"{spec.name} checkpoint not present (run: git lfs pull)")
    model = get_loaded(spec)
    assert model is not None, f"{spec.name} failed to load — see logs"
    return model


def _fits_bytes(spectrum: np.ndarray, cadence: float = 0.25) -> bytes:
    """An e-CALLISTO-shaped file: uint8 image plus an AXES table (descending MHz)."""
    from astropy.io import fits

    n_freq, n_time = spectrum.shape
    freq = np.linspace(80.0, 45.0, n_freq)
    time = np.arange(n_time) * cadence
    axes = fits.BinTableHDU.from_columns(
        [
            fits.Column(name="TIME", format=f"{n_time}D", array=time[np.newaxis]),
            fits.Column(name="FREQUENCY", format=f"{n_freq}D", array=freq[np.newaxis]),
        ],
        name="AXES",
    )
    buffer = io.BytesIO()
    fits.HDUList([fits.PrimaryHDU(spectrum.astype(np.uint8)), axes]).writeto(buffer)
    return buffer.getvalue()


def test_checkpoint_loads_strictly_with_its_class_order(loaded):
    # Label order maps softmax indices to names and must not drift.
    assert loaded.class_names == (
        "No_Burst", "RFI", "Type II", "Type III", "Type IIIG", "Other",
    )
    assert loaded.views == ("crop", "context", "quiet_context")
    # 224x224 is what every view is resized to; anything else is mis-fed.
    assert loaded.crop.target_shape == (224, 224)


def test_scoring_uses_the_calibrated_settings(loaded):
    # The registry publishes the threshold so alert gating works before a load;
    # it must agree with what the checkpoint actually contains.
    assert loaded.threshold == pytest.approx(
        registry.CCM_V200.metrics["threshold"], abs=1e-9
    )
    assert loaded.finder == {
        "threshold": 0.35, "adaptive": True, "min_area": 60, "max_regions": 24,
        "hysteresis": 0.65,
    }
    assert loaded.type_strength == pytest.approx(0.5)
    assert set(loaded.type_adjustment) == {"Type II", "Type III", "Type IIIG", "Other"}


def test_models_are_cached_not_reloaded(loaded):
    assert get_loaded(registry.CCM_V200) is loaded


def test_a_featureless_file_is_no_burst_without_running_the_network(loaded):
    # Flat after background subtraction: nothing reaches the finder's floor, so
    # there are no regions and the burst probability is exactly zero.
    record = predict_bytes(
        _fits_bytes(np.full((200, 3600), 120)), "BIR_20260615_020000_01.fit.gz"
    )
    assert record is not None
    assert record["predicted_label"] == "No_Burst"
    assert record["burst_probability"] == 0.0
    assert record["model_id"] == "ccm-2.0.0"
    assert "burst_type" not in record


def test_a_bright_drifting_lane_produces_a_consistent_record(loaded):
    rng = np.random.default_rng(0)
    spectrum = rng.normal(120, 2, size=(200, 3600))
    # A fast-drifting lane from the top of the band to the bottom, ~6 s long.
    for row in range(20, 180):
        col = 1500 + (row - 20) // 8
        spectrum[row, col:col + 8] += 60
    record = predict_bytes(_fits_bytes(np.clip(spectrum, 0, 255)), "BIR_20260615_020000_01.fit.gz")

    assert record is not None
    assert 0.0 <= record["burst_probability"] <= 1.0
    assert record["decision_threshold"] == pytest.approx(loaded.threshold)
    is_burst = record["burst_probability"] >= loaded.threshold
    assert record["predicted_label"] == ("Burst" if is_burst else "No_Burst")
    if is_burst:
        # Type IIIG is never reported; it is folded into Type III.
        assert record["burst_type"] in {"Type II", "Type III", "Other"}
        assert set(record["type_probabilities"]) == {"No_Burst", "Type II", "Type III", "Other"}
        assert record["type_regions"]
        region = record["type_regions"][0]
        assert 45.0 <= region["freq_min_mhz"] <= region["freq_max_mhz"] <= 80.0
        assert 0 <= region["start_seconds"] <= region["end_seconds"] <= 900
