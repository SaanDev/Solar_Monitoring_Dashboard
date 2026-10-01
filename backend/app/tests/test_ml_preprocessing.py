"""BnB v1.0's inputs and verdict, without torch or the checkpoint.

Two kinds of check:

* **Golden values.** The image and metadata vector built for each synthetic file
  in :mod:`app.tests.bnb_cases` must match what the CALLISTO Trainer built for
  the same file (the probabilities are checked in test_ml_checkpoints.py).
* **Behaviour.** What each preprocessing step exists for, and how a probability
  becomes a record.
"""
import numpy as np
import pytest

from app.ml import inference as inf
from app.ml import registry
from app.ml.metadata_features import meta_vector, station_index
from app.ml.preprocessing import (
    header_frequency_bounds,
    normalize_full_spectrum,
    read_axes,
    read_spectrum_bytes,
    whole_file_tensor,
)
from app.tests.bnb_cases import CASES, case_bytes

_PREP = {
    "background_method": "plotutil_median_db",
    "normalization": "db_window",
    "db_vmin": -1.0,
    "db_vmax": 8.0,
}
# The two cases' stations as the checkpoint's vocabulary indexes them.
_VOCAB = {"ALASKA-COHOE": 2, "BIR": 11}
_THRESHOLD = registry.BNB_V100.metrics["threshold"]


# ── Golden values ────────────────────────────────────────────────────────────


@pytest.mark.parametrize("case", CASES, ids=[c["filename"] for c in CASES])
def test_inputs_match_the_trainer(case):
    spectrum, metadata = read_spectrum_bytes(case_bytes(case), case["filename"])
    assert {k: metadata[k] for k in case["metadata"]} == case["metadata"]

    vector = meta_vector(metadata, _VOCAB)
    assert vector.dtype == np.float32
    np.testing.assert_allclose(vector, case["vector"], rtol=0, atol=1e-7)

    image = whole_file_tensor(normalize_full_spectrum(spectrum, _PREP))
    assert image.shape == (1, 224, 224)
    assert float(image.sum(dtype=np.float64)) == pytest.approx(case["input_sum"], abs=1e-3)
    np.testing.assert_allclose(image[0, ::32, ::32].ravel(), case["samples"], rtol=0, atol=1e-6)


# ── Normalization ────────────────────────────────────────────────────────────


def test_background_is_subtracted_over_the_full_time_axis():
    raw = np.full((10, 400), 100.0, dtype=np.float32)
    raw[:, 100:110] = 160.0  # a short burst in every channel
    normalized = normalize_full_spectrum(raw, _PREP)
    # The median over the whole file is the quiet level, so the burst survives.
    assert normalized[:, 105].min() > 0.9
    assert normalized[:, 300].max() == pytest.approx(1 / 9, abs=1e-6)


def test_nan_and_inf_are_replaced_before_normalizing():
    raw = np.full((5, 50), 100.0, dtype=np.float32)
    raw[2, 10] = np.nan
    raw[3, 20] = np.inf
    assert np.isfinite(normalize_full_spectrum(raw, _PREP)).all()


def test_an_unsupported_preprocessing_config_is_refused():
    with pytest.raises(ValueError):
        normalize_full_spectrum(np.zeros((4, 8)), {**_PREP, "normalization": "median_mad"})


# ── Frequency range ──────────────────────────────────────────────────────────


class _Table:
    def __init__(self, **columns):
        self._columns = columns
        self.columns = type("C", (), {"names": list(columns)})()
        self.data = self
        self.name = "AXES"

    def __getitem__(self, key):
        return self._columns[key]


def test_axes_come_from_the_table_as_offsets_from_the_first_sample():
    table = _Table(TIME=np.array([[3600.0, 3600.25, 3600.5]]), FREQUENCY=np.array([[80.0, 60.0]]))
    time_s, freq = read_axes([None, table], n_freq=2, n_time=3)
    assert time_s.tolist() == [0.0, 0.25, 0.5]
    assert freq.tolist() == [80.0, 60.0]


def test_an_axes_table_of_the_wrong_length_is_ignored():
    table = _Table(TIME=np.arange(5.0), FREQUENCY=np.arange(2.0))
    assert read_axes([None, table], n_freq=2, n_time=3) == (None, None)


def test_header_frequencies_are_read_like_training_did():
    # Placeholders on this archive, but what the model saw for such files.
    assert header_frequency_bounds({"CRVAL2": 200.0, "CDELT2": -1.0}, n_freq=3) == (198.0, 200.0)
    assert header_frequency_bounds({"CRVAL2": 45.0, "CDELT2": 0.5, "NAXIS2": 5}) == (45.0, 47.0)
    assert header_frequency_bounds({"CRVAL2": 200.0}, n_freq=3) == (None, None)


# ── Metadata vector ──────────────────────────────────────────────────────────


def test_station_names_match_exactly_as_training_did():
    # The vocabulary was built from trimmed names with no case folding.
    assert station_index(" BIR ", _VOCAB) == 11
    assert station_index("bir", _VOCAB) == 0
    assert station_index(None, _VOCAB) == 0


def test_missing_date_and_frequencies_are_zeros():
    vector = meta_vector({"station": "BIR", "date": "not a date"}, _VOCAB)
    assert vector.tolist() == [11.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]


# ── The verdict ──────────────────────────────────────────────────────────────


def _loaded() -> inf.LoadedModel:
    return inf.LoadedModel(
        spec=registry.BNB_V100, model=None, config={}, device="cpu",
        threshold=_THRESHOLD, preprocessing=_PREP, target_shape=(224, 224),
        station_vocab=_VOCAB,
    )


def test_a_probability_at_the_threshold_is_a_burst():
    record = inf.build_record(_loaded(), _THRESHOLD, "dir/BIR_20260615_020000_01.fit.gz")
    assert record["predicted_label"] == "Burst"
    assert record["file_name"] == "BIR_20260615_020000_01.fit.gz"
    assert record["decision_threshold"] == _THRESHOLD
    assert record["confidence"] == _THRESHOLD
    assert record["model_id"] == "bnb-1.0.0"
    assert record["model_name"] == "BnB v1.0"


def test_a_probability_below_it_is_no_burst_and_never_typed():
    record = inf.build_record(_loaded(), 0.30, "x.fit.gz")
    assert record["predicted_label"] == "No_Burst"
    assert record["confidence"] == pytest.approx(0.70)
    assert "burst_type" not in record and "type_regions" not in record


@pytest.mark.parametrize(
    "probability, level",
    [
        (0.30, "No alert"),
        (0.56, "No alert"),               # just under the threshold
        (_THRESHOLD, "Possible burst"),   # the threshold reads as 0.5
        (0.85, "Likely burst"),
        (0.95, "High-confidence burst"),
    ],
)
def test_alert_levels_are_relative_to_the_threshold(probability, level):
    assert inf.relative_alert_level(probability, _THRESHOLD) == level
