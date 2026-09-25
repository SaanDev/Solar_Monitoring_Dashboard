"""Region proposals and cropping for the burst-type stage.

Two things are being protected here:

* The whole-file tensor must stay **bit-identical** after the pipeline was split
  into normalize-then-resize, or CCM v1.0.0's stored results stop being
  comparable with new ones.
* The geometry floors must keep rejecting e-CALLISTO's periodic narrow-band
  calibration marker. Without them a dozen of those blobs fill every candidate
  slot and a genuine Type III file gets typed from an artifact instead.

Pure NumPy/SciPy — no torch, no checkpoints.
"""
import numpy as np
import pytest

from app.ml import regions as reg
from app.ml.preprocessing import (
    crop_from_normalized,
    db_window_normalize,
    clean_invalid_values,
    expand_box,
    normalize_full_spectrum,
    plotutil_median_db,
    preprocess_array,
    resize_spectrum,
    whole_file_box,
)

CONFIG = {
    "data": {"target_shape": [224, 224]},
    "preprocessing": {"db_vmin": -1.0, "db_vmax": 8.0},
}


def _blank(n_freq: int = 200, n_time: int = 600) -> np.ndarray:
    return np.zeros((n_freq, n_time), dtype=np.float32)


# ── Pipeline equivalence ──────────────────────────────────────────────────────


def test_split_pipeline_is_bit_identical_to_the_original():
    rng = np.random.default_rng(7)
    spectrum = rng.normal(120.0, 8.0, size=(200, 900)).astype(np.float32)

    # The pre-split pipeline, inline.
    data = clean_invalid_values(spectrum)
    data = plotutil_median_db(data)
    data = db_window_normalize(data, -1.0, 8.0)
    expected = resize_spectrum(data, (224, 224))[np.newaxis, :, :].astype(np.float32)

    assert np.array_equal(preprocess_array(spectrum, CONFIG), expected)


def test_whole_file_crop_equals_the_whole_file_tensor():
    # The binary stage takes its input through crop_from_normalized so one
    # normalize pass feeds both stages; that path must not change the tensor.
    rng = np.random.default_rng(11)
    spectrum = rng.normal(100.0, 5.0, size=(180, 700)).astype(np.float32)
    normalized = normalize_full_spectrum(spectrum, CONFIG)
    crop = crop_from_normalized(normalized, whole_file_box(spectrum.shape), (224, 224))
    assert np.array_equal(crop, preprocess_array(spectrum, CONFIG))


def test_background_is_subtracted_over_the_full_time_axis():
    # Cropping first would make a burst its own baseline and erase it. A bright
    # patch covering a small slice of time must survive normalization.
    spectrum = np.full((100, 800), 100.0, dtype=np.float32)
    spectrum[40:60, 300:340] = 400.0
    normalized = normalize_full_spectrum(spectrum, CONFIG)
    patch = normalized[40:60, 300:340]
    assert patch.min() > 0.9          # clipped high against the dB window
    assert normalized[0, 0] == pytest.approx(0.111, abs=0.01)  # quiet background


# ── Cropping ──────────────────────────────────────────────────────────────────


def test_crop_slices_the_requested_box_and_resizes():
    normalized = _blank(120, 400)
    normalized[30:50, 100:160] = 1.0
    crop = crop_from_normalized(normalized, (30, 50, 100, 160), (224, 224))
    assert crop.shape == (1, 224, 224)
    assert crop.min() == pytest.approx(1.0)   # the box was entirely the bright patch


def test_expand_box_is_a_no_op_without_a_margin():
    assert expand_box((10, 20, 5, 25), (100, 100)) == (10, 20, 5, 25)


def test_expand_box_grows_by_the_margin_and_clips_to_the_array():
    # 50% of a 10-row / 20-col box is 5 rows / 10 cols on each side.
    assert expand_box((20, 30, 40, 60), (100, 200), context_margin=0.5) == (15, 35, 30, 70)
    # Clipped at the edges rather than running negative or past the end.
    assert expand_box((0, 4, 0, 4), (10, 10), context_margin=1.0) == (0, 8, 0, 8)


def test_expand_box_enforces_a_minimum_extent_at_an_edge():
    # Growing away from the boundary, since there is no room on the other side.
    assert expand_box((0, 1, 0, 1), (50, 50), min_rows=8, min_cols=4) == (0, 8, 0, 4)
    assert expand_box((49, 50, 49, 50), (50, 50), min_rows=8, min_cols=4) == (42, 50, 46, 50)


def test_degenerate_box_is_grown_to_the_minimum_extent():
    # A zero-height box is widened rather than rejected, so a one-pixel-tall
    # proposal still produces a usable crop instead of an exception mid-scan.
    crop = crop_from_normalized(_blank(50, 50), (10, 10, 0, 20), (224, 224))
    assert crop.shape == (1, 224, 224)


def test_non_2d_normalized_input_is_rejected():
    with pytest.raises(ValueError):
        crop_from_normalized(np.zeros((1, 50, 50), dtype=np.float32), (0, 10, 0, 10))


# ── Region finding ────────────────────────────────────────────────────────────


def test_finds_a_bright_rectangle_with_exact_bounds():
    normalized = _blank()
    normalized[40:80, 100:200] = 0.9
    found = reg.find_candidate_regions(normalized, threshold=0.35)
    assert len(found) == 1
    r = found[0]
    assert (r.row0, r.row1, r.col0, r.col1) == (40, 80, 100, 200)
    assert r.area == 40 * 100
    assert r.peak == pytest.approx(0.9)


def test_regions_are_ordered_largest_first():
    normalized = _blank()
    normalized[10:30, 10:60] = 0.9      # 1000 px
    normalized[100:160, 100:200] = 0.9  # 6000 px
    found = reg.find_candidate_regions(normalized, threshold=0.35)
    assert [r.area for r in found] == [6000, 1000]


def test_nothing_above_threshold_yields_no_regions():
    assert reg.find_candidate_regions(_blank() + 0.1, threshold=0.35) == []


def test_min_area_rejects_specks():
    normalized = _blank()
    normalized[50:56, 50:56] = 0.9  # 36 px, below the 60 px floor
    assert reg.find_candidate_regions(normalized, threshold=0.35, min_area=60) == []


def test_narrow_band_calibration_marker_is_rejected():
    """The defect this filter exists for.

    e-CALLISTO files carry a periodic marker: a couple of frequency channels at a
    band edge, repeating every ~60 s. It clears both the brightness threshold and
    the area floor, so without a frequency-extent floor a swarm of them crowds the
    real burst out of the candidate list entirely.
    """
    normalized = _blank(200, 3600)
    # Three frequency rows x 200 samples, repeated with gaps so each is its own
    # connected component: area 600 apiece, well over the area floor, but far too
    # narrow in frequency to be a burst.
    for col in range(0, 3600, 300):
        normalized[0:3, col : col + 200] = 0.95
    # One genuine burst: a real frequency sweep, but *smaller in area* than the
    # markers — which is exactly the case that broke on real data.
    normalized[60:100, 1000:1012] = 0.95

    unfiltered = reg.find_candidate_regions(
        normalized, threshold=0.35, min_rows=1, min_cols=1, max_candidates=8
    )
    assert len(unfiltered) == 8
    # The burst is squeezed out: every slot went to a marker.
    assert all(r.row1 - r.row0 == 3 for r in unfiltered)

    filtered = reg.find_candidate_regions(normalized, threshold=0.35, max_candidates=8)
    assert len(filtered) == 1
    assert (filtered[0].row0, filtered[0].row1) == (60, 100)


def test_max_candidates_caps_the_list():
    normalized = _blank(200, 3600)
    for i in range(12):
        normalized[20:60, i * 200 : i * 200 + 40] = 0.9
    assert len(reg.find_candidate_regions(normalized, threshold=0.35, max_candidates=5)) == 5


def test_non_2d_input_is_rejected():
    with pytest.raises(ValueError):
        reg.find_candidate_regions(np.zeros((2, 10, 10), dtype=np.float32))


# ── Adaptive threshold ────────────────────────────────────────────────────────


def test_adaptive_threshold_never_exceeds_the_absolute_one():
    bright = _blank() + 0.9
    assert reg.resolve_threshold(bright, absolute=0.35) == pytest.approx(0.35)


def test_adaptive_threshold_drops_for_a_low_contrast_spectrum():
    faint = _blank()
    faint[40:60, 100:200] = 0.25  # brightest signal sits below the absolute floor
    resolved = reg.resolve_threshold(faint, absolute=0.35)
    assert reg.ADAPTIVE_FLOOR <= resolved < 0.35


def test_adaptive_threshold_respects_its_floor():
    # An almost entirely blank spectrum must not push the threshold to ~0, which
    # would turn pure noise into candidate regions.
    assert reg.resolve_threshold(_blank(), absolute=0.35) == pytest.approx(reg.ADAPTIVE_FLOOR)


def test_adaptive_can_be_disabled():
    assert reg.resolve_threshold(_blank(), absolute=0.42, adaptive=False) == pytest.approx(0.42)


# ── Dominant type ─────────────────────────────────────────────────────────────


def _region(area: int, burst_type: str | None, confidence: float | None = 0.9) -> reg.Region:
    return reg.Region(
        row0=0, row1=10, col0=0, col1=10, area=area, peak=0.9,
        burst_type=burst_type, confidence=confidence,
    )


def test_dominant_type_prefers_area_over_confidence():
    # A big region is more likely the real event; a small, very confident speck is
    # more likely interference the classifier still had to put in some class.
    found = [_region(500, "Other", 0.999), _region(7000, "Type III", 0.62)]
    assert reg.dominant_type(found) == "Type III"


def test_dominant_type_ignores_untyped_regions():
    assert reg.dominant_type([_region(9000, None), _region(100, "Type II")]) == "Type II"


def test_dominant_type_is_none_when_nothing_was_typed():
    assert reg.dominant_type([]) is None
    assert reg.dominant_type([_region(9000, None)]) is None


# ── Physical units ────────────────────────────────────────────────────────────


def test_region_to_axes_uses_the_per_row_frequency_axis():
    # Row 0 is the highest frequency (the FREQUENCY column is stored descending),
    # so the reported low/high must be ordered, not taken from the row order.
    freq_axis = np.linspace(80.0, 20.0, 200)
    metadata = {"n_freq": 200, "n_time": 3600, "freq_axis": freq_axis,
                "freq_min_mhz": 20.0, "freq_max_mhz": 80.0}
    described = reg.region_to_axes(_region(100, "Type III", 0.8), metadata, 900)
    assert described["freq_min_mhz"] < described["freq_max_mhz"]
    assert described["freq_max_mhz"] == pytest.approx(80.0)
    assert described["burst_type"] == "Type III"
    assert described["confidence"] == pytest.approx(0.8)


def test_region_to_axes_interpolates_when_there_is_no_frequency_axis():
    metadata = {"n_freq": 100, "n_time": 1800, "freq_axis": None,
                "freq_min_mhz": 10.0, "freq_max_mhz": 110.0}
    region = reg.Region(row0=0, row1=100, col0=0, col1=1800, area=1, peak=1.0,
                        burst_type="Type II", confidence=0.7)
    described = reg.region_to_axes(region, metadata, 900)
    assert described["freq_min_mhz"] == pytest.approx(10.0)
    assert described["freq_max_mhz"] == pytest.approx(110.0)


def test_region_to_axes_maps_columns_to_seconds_within_the_segment():
    metadata = {"n_freq": 100, "n_time": 1800, "freq_axis": None,
                "freq_min_mhz": 10.0, "freq_max_mhz": 110.0}
    region = reg.Region(row0=0, row1=10, col0=900, col1=1080, area=1, peak=1.0)
    described = reg.region_to_axes(region, metadata, 900)  # 900 s over 1800 samples
    assert described["start_seconds"] == 450
    assert described["end_seconds"] == 540
    # Never reports past the end of the segment.
    full = reg.Region(row0=0, row1=10, col0=0, col1=1800, area=1, peak=1.0)
    assert reg.region_to_axes(full, metadata, 900)["end_seconds"] == 900


def test_region_to_axes_survives_missing_frequency_metadata():
    described = reg.region_to_axes(_region(10, "Other"), {"n_time": 1800}, 900)
    assert described["freq_min_mhz"] is None
    assert described["freq_max_mhz"] is None
