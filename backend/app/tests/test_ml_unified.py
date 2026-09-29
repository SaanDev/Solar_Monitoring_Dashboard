"""CCM v2.0's scoring logic, without torch or the checkpoint.

Two kinds of check:

* **Golden values.** The model only means anything on inputs built exactly the
  way its training samples were, and it answers confidently either way, so a
  numeric drift in the port would never announce itself. The expected region
  boxes and 28-feature vectors below were computed by the CALLISTO Trainer
  itself (``RegionEncoder``) on the deterministic synthetic spectrum defined
  here; the port must reproduce them.
* **The verdict.** How probabilities become a decision: burst evidence against
  the calibrated threshold, the type-frequency correction, and Type IIIG folded
  into Type III *before* the type is chosen.
"""
import numpy as np
import pytest

from app.ml import inference as inf
from app.ml.physics import measure_burst
from app.ml.preprocessing import SpectrumAxes, normalize_full_spectrum
from app.ml.region_features import FEATURE_COUNT, feature_vector, file_context, measure_region
from app.ml.regions import Region, find_candidate_regions, resolve_threshold

_PREP = {
    "background_method": "plotutil_median_db",
    "normalization": "db_window",
    "db_vmin": -1.0,
    "db_vmax": 8.0,
}
_CLASSES = ("No_Burst", "RFI", "Type II", "Type III", "Type IIIG", "Other")
_THRESHOLD = 0.7975836745463312


def _synthetic_spectrum() -> np.ndarray:
    """Deterministic (no RNG) 200 x 1800 spectrum with bursts and interference."""
    rows, cols = np.mgrid[0:200, 0:1800].astype(np.float64)
    data = 100 + 2.0 * np.sin(rows * 1.7 + cols * 0.13) * np.cos(cols * 0.071 + rows * 0.9)
    # A fast-drifting lane (Type III-like): row 20 -> 180 over ~20 s.
    for row in range(20, 180):
        col = 600 + (row - 20) // 2
        data[row, col:col + 6] += 40
    # A slow lane (Type II-like), fainter and patchy.
    for row in range(60, 140):
        col = 1100 + (row - 60) * 4
        data[row, col:col + 12] += 18 + 6 * np.sin(row)
    # A narrowband carrier across the whole file.
    data[150:152, :] += 25
    # A broadband impulse every 60 s (240 samples).
    data[:, 120::240] += 30
    return data.astype(np.float32)


# Computed by the CALLISTO Trainer on _synthetic_spectrum() with the axes and
# RFI channels in test_features_match_the_trainer: (box, area, features).
_GOLDEN = [
    ((0, 200, 600, 685), 1158, [1.893129, 1.694759, 1.556303, 1.342423, -2.217889, -2.421022, 0.514007, 1.000000, 0.006872, 1.000000, 0.221226, 0.000000, 0.273001, 1.113943, 0.068118, 0.434972, 0.005518, 0.569975, 0.892665, 0.047222, 0.010000, 0.083333, 0.767732, 0.386900, 0.095960, 0.463452, 0.600925, 0.000000]),
    ((0, 200, 1100, 1428), 1157, [1.849258, 1.750695, 1.556303, 1.917768, -1.268410, -1.463662, 0.999314, 1.000000, 0.008010, 1.000000, 0.185130, 1.557507, 0.096910, 0.602060, 0.017637, 0.434972, 0.019975, 0.680584, 0.892665, 0.182222, 0.010000, 0.083333, 0.767732, 0.503439, 0.095960, 0.463452, 0.600925, 0.000000]),
    ((0, 200, 120, 121), 200, [0.000000, 0.000000, 0.000000, 0.000000, 0.000000, 0.000000, 0.000000, 0.000000, 0.008658, 1.000000, 1.000000, 0.000000, 0.096910, 2.303196, 1.000000, 0.434972, 0.000000, 0.000000, 0.000000, 0.000556, 0.010000, 0.000000, 0.767732, 0.060206, 0.095960, 0.463452, 0.600925, 0.000000]),
    ((0, 200, 360, 361), 200, [0.000000, 0.000000, 0.000000, 0.000000, 0.000000, 0.000000, 0.000000, 0.000000, 0.008658, 1.000000, 1.000000, 0.000000, 0.096910, 2.303196, 1.000000, 0.434972, 0.000000, 0.467180, 0.892665, 0.000556, 0.010000, 0.000000, 0.767732, 0.060206, 0.095960, 0.463452, 0.600925, 0.000000]),
]


# ── Golden values ────────────────────────────────────────────────────────────


def test_features_match_the_trainer():
    spectrum = _synthetic_spectrum()
    axes = SpectrumAxes(
        time_s=np.arange(1800) * 0.25, freq_mhz=np.linspace(80.0, 45.0, 200), source="axes_table"
    )
    normalized = normalize_full_spectrum(spectrum, _PREP)
    found = find_candidate_regions(
        normalized, threshold=resolve_threshold(normalized, 0.35, True),
        min_area=60, max_candidates=24, hysteresis=0.65,
    )
    context = file_context(normalized, axes, rfi_channels=[45.35, 80.0])

    assert len(found) == 7
    for region, (box, area, expected) in zip(found, _GOLDEN):
        assert (region.row0, region.row1, region.col0, region.col1) == box
        assert region.area == area
        physics = measure_burst(normalized, axes, *box)
        features = feature_vector(physics, measure_region(context, *box, physics))
        assert features.shape == (FEATURE_COUNT,) == (28,)
        np.testing.assert_allclose(features, expected, atol=2e-6)


# ── Type-frequency correction ────────────────────────────────────────────────


def test_type_priors_only_move_probability_between_burst_types():
    probabilities = np.array([[0.10, 0.05, 0.40, 0.25, 0.10, 0.10]])
    adjustment = {"Type II": -1.52, "Type III": 1.05, "Type IIIG": 0.22, "Other": 0.25}
    adjusted = inf.adjust_type_probabilities(probabilities, _CLASSES, adjustment, 0.5)

    # Non-burst classes, and therefore burst evidence, are untouched...
    np.testing.assert_allclose(adjusted[0, :2], probabilities[0, :2])
    assert adjusted[0, 2:].sum() == pytest.approx(probabilities[0, 2:].sum())
    # ...while the rare Type II gives way to the common Type III.
    assert adjusted[0, 2] < probabilities[0, 2]
    assert adjusted[0, 3] > probabilities[0, 3]


def test_zero_strength_leaves_the_types_as_trained():
    probabilities = np.array([[0.1, 0.1, 0.4, 0.2, 0.1, 0.1]])
    adjusted = inf.adjust_type_probabilities(probabilities, _CLASSES, {"Type II": -1.0}, 0.0)
    np.testing.assert_allclose(adjusted, probabilities)


# ── Region verdict ───────────────────────────────────────────────────────────


def _region(area: int = 100) -> Region:
    return Region(row0=0, row1=10, col0=0, col1=10, area=area, peak=1.0)


def test_type_iii_and_iiig_are_added_before_the_type_is_chosen():
    # Other is the largest single class, but III + IIIG outweighs it.
    row = np.array([0.063, 0.0, 0.010, 0.401, 0.096, 0.430])
    scored = inf.decide_region(_region(), row, _CLASSES, _THRESHOLD)

    assert scored.is_burst
    assert scored.burst_type == "Type III"
    assert scored.probabilities["Type III"] == pytest.approx(0.497)
    assert "Type IIIG" not in scored.probabilities
    # Confidence in the type is conditional on the region being a burst.
    assert scored.type_confidence == pytest.approx(0.497 / 0.937)


def test_rfi_is_reported_as_no_burst_and_counts_against_the_evidence():
    row = np.array([0.05, 0.20, 0.0, 0.70, 0.05, 0.0])
    scored = inf.decide_region(_region(), row, _CLASSES, _THRESHOLD)

    assert scored.burst_evidence == pytest.approx(0.75)
    assert scored.probabilities["No_Burst"] == pytest.approx(0.25)
    assert "RFI" not in scored.probabilities
    # 0.75 is under the calibrated threshold, however confident the type.
    assert not scored.is_burst
    assert scored.burst_type is None and scored.type_confidence is None


def test_the_threshold_is_inclusive():
    row = np.array([0.25, 0.0, 0.75, 0.0, 0.0, 0.0])
    assert inf.decide_region(_region(), row, _CLASSES, 0.75).is_burst
    assert not inf.decide_region(_region(), row, _CLASSES, 0.76).is_burst


# ── File record ──────────────────────────────────────────────────────────────


class _Spec:
    id = "ccm-2.0.0"
    name = "CCM v2.0"


class _Loaded:
    spec = _Spec()
    threshold = _THRESHOLD


_AXES = SpectrumAxes(
    time_s=np.arange(3600) * 0.25, freq_mhz=np.linspace(80.0, 45.0, 200), source="axes_table"
)


def _scored(area: int, row: list[float]) -> inf.ScoredRegion:
    return inf.decide_region(_region(area), np.array(row), _CLASSES, _THRESHOLD)


def test_a_file_takes_the_type_of_its_largest_burst_region():
    regions = [
        _scored(80, [0.01, 0.0, 0.98, 0.01, 0.0, 0.0]),    # small, very confident II
        _scored(900, [0.05, 0.0, 0.05, 0.60, 0.30, 0.0]),  # large III (+ IIIG)
        _scored(5000, [0.90, 0.10, 0.0, 0.0, 0.0, 0.0]),   # largest, but background
    ]
    record = inf.build_record(_Loaded(), regions, _AXES, "BIR_20260615_020000_01.fit.gz")

    assert record["predicted_label"] == "Burst"
    assert record["burst_type"] == "Type III"
    assert record["type_confidence"] == pytest.approx(0.90 / 0.95)
    # The file's probability is its strongest region's evidence.
    assert record["burst_probability"] == pytest.approx(0.99)
    assert record["type_model_id"] == "ccm-2.0.0"
    # Only burst regions are listed, with their own types.
    assert [r["burst_type"] for r in record["type_regions"]] == ["Type II", "Type III"]
    assert record["file_name"] == "BIR_20260615_020000_01.fit.gz"


def test_a_file_with_no_burst_region_carries_no_type():
    regions = [_scored(900, [0.40, 0.30, 0.10, 0.10, 0.05, 0.05])]
    record = inf.build_record(_Loaded(), regions, _AXES, "x.fit.gz")

    assert record["predicted_label"] == "No_Burst"
    assert record["burst_probability"] == pytest.approx(0.30)
    assert record["confidence"] == pytest.approx(0.70)
    assert "burst_type" not in record and "type_regions" not in record


def test_a_file_with_no_regions_is_certain_no_burst():
    record = inf.build_record(_Loaded(), [], _AXES, "x.fit.gz")
    assert record["predicted_label"] == "No_Burst"
    assert record["burst_probability"] == 0.0
    assert record["alert_level"] == "No alert"


@pytest.mark.parametrize(
    "probability, level",
    [
        (0.30, "No alert"),
        (0.79, "No alert"),               # just under the threshold
        (_THRESHOLD, "Possible burst"),   # the threshold reads as 0.5
        (0.93, "Likely burst"),
        (0.97, "High-confidence burst"),
    ],
)
def test_alert_levels_are_relative_to_the_threshold(probability, level):
    assert inf.relative_alert_level(probability, _THRESHOLD) == level
