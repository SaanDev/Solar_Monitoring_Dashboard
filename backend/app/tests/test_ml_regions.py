"""Preprocessing, region views and the candidate-region finder for CCM v2.0.

Pure NumPy/SciPy — no torch, no checkpoint — so these run in the default venv.
Exact agreement with the CALLISTO Trainer on real files is checked separately
(the golden values in test_ml_unified.py); these pin the behaviour each step
exists for.
"""
import numpy as np
import pytest

from app.ml import regions as reg
from app.ml.preprocessing import (
    CropConfig,
    PixelBox,
    SpectrumAxes,
    context_view,
    crop_view,
    normalize_full_spectrum,
    quiet_normalized_spectrum,
    read_axes,
    region_views,
    synthesize_axes,
)

_PREP = {
    "background_method": "plotutil_median_db",
    "normalization": "db_window",
    "db_vmin": -1.0,
    "db_vmax": 8.0,
}
_CROP = CropConfig()


def _quiet(n_freq: int = 40, n_time: int = 600) -> np.ndarray:
    return np.zeros((n_freq, n_time), dtype=np.float32)


# ── Normalization ────────────────────────────────────────────────────────────


def test_background_is_subtracted_over_the_full_time_axis():
    raw = np.full((10, 400), 100.0, dtype=np.float32)
    raw[:, 100:110] = 160.0  # a short burst in every channel
    normalized = normalize_full_spectrum(raw, _PREP)
    # The median over the whole file is the quiet level, so the burst survives.
    assert normalized[:, 105].min() > 0.9
    assert normalized[:, 300].max() == pytest.approx(1 / 9, abs=1e-6)


def test_quiet_background_keeps_a_long_continuum_visible():
    raw = np.full((10, 400), 100.0, dtype=np.float32)
    raw[:, :300] = 130.0  # emission lasting 75% of the file
    median_based = normalize_full_spectrum(raw, _PREP)
    quiet_based = quiet_normalized_spectrum(raw, _PREP)
    # The median sits inside the continuum, which then reads as background...
    assert median_based[:, 100].max() < 0.2
    # ...while the quiet part's 10th percentile does not.
    assert quiet_based[:, 100].min() > 0.9


def test_nan_and_inf_are_replaced_before_normalizing():
    raw = np.full((5, 50), 100.0, dtype=np.float32)
    raw[2, 10] = np.nan
    raw[3, 20] = np.inf
    assert np.isfinite(normalize_full_spectrum(raw, _PREP)).all()


def test_an_unsupported_preprocessing_config_is_refused():
    with pytest.raises(ValueError):
        normalize_full_spectrum(_quiet(), {**_PREP, "normalization": "median_mad"})


# ── Views ────────────────────────────────────────────────────────────────────


def test_crop_view_is_the_exact_region_resized():
    normalized = _quiet()
    normalized[10:20, 100:150] = 1.0
    view = crop_view(normalized, PixelBox(10, 20, 100, 150), _CROP)
    assert view.shape == (224, 224)
    assert view.min() == pytest.approx(1.0)  # nothing outside the box leaks in


def test_context_view_covers_the_full_band_and_keeps_one_sample_spikes():
    from app.ml.preprocessing import resize_spectrum

    normalized = _quiet(n_time=4000)
    normalized[:, 3200] = 1.0  # a one-sample broadband impulse
    # A 192-sample region is widened by 240 each side: a 672-sample strip
    # (cols 2660-3332) that reaches the impulse, which the crop itself does not.
    box = PixelBox(10, 20, 2900, 3092)
    assert crop_view(normalized, box, _CROP).max() == 0.0
    # Max-pooling before the resize keeps the spike at full strength...
    assert context_view(normalized, box, _CROP).max() == pytest.approx(1.0)
    # ...where a plain linear resize of the same strip samples right past it.
    assert resize_spectrum(normalized[:, 2660:3332]).max() < 0.5


def test_region_views_stack_in_the_models_order():
    normalized = _quiet()
    quiet = np.ones_like(normalized)
    views = region_views(
        normalized, PixelBox(0, 10, 0, 10), _CROP, ("crop", "context", "quiet_context"), quiet
    )
    assert views.shape == (3, 224, 224)
    assert views[2].min() == 1.0  # the third view reads the quiet array
    with pytest.raises(ValueError):
        region_views(normalized, PixelBox(0, 10, 0, 10), _CROP, ("quiet_context",))


def test_an_empty_box_is_rejected():
    with pytest.raises(ValueError):
        PixelBox(5, 5, 0, 10)


# ── Axes ─────────────────────────────────────────────────────────────────────


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


def test_synthesized_axes_follow_the_header_like_training_did():
    header = {"CDELT1": 0.5, "CRVAL2": 200.0, "CDELT2": -1.0}
    time_s, freq = synthesize_axes(header, n_freq=3, n_time=4)
    assert time_s.tolist() == [0.0, 0.5, 1.0, 1.5]
    assert freq.tolist() == [200.0, 199.0, 198.0]


# ── Finder ───────────────────────────────────────────────────────────────────


def test_finds_a_bright_rectangle_with_exact_bounds():
    normalized = _quiet()
    normalized[5:15, 100:130] = 1.0
    found = reg.find_candidate_regions(normalized, threshold=0.35, hysteresis=None)
    assert len(found) == 1
    r = found[0]
    assert (r.row0, r.row1, r.col0, r.col1) == (5, 15, 100, 130)
    assert r.area == 300 and r.peak == 1.0


def test_hysteresis_does_not_widen_a_sharp_edged_region():
    normalized = _quiet()
    normalized[5:15, 100:130] = 1.0
    r = reg.find_candidate_regions(normalized, threshold=0.35)[0]
    assert (r.row0, r.row1, r.col0, r.col1) == (5, 15, 100, 130)


def test_hysteresis_grows_a_seed_through_its_faint_surroundings():
    normalized = _quiet()
    normalized[5:15, 100:130] = 0.30   # below the threshold, above 0.65 x it
    normalized[8:11, 110:113] = 1.0    # a small bright core
    plain = reg.find_candidate_regions(normalized, threshold=0.35, hysteresis=None)
    grown = reg.find_candidate_regions(normalized, threshold=0.35, hysteresis=0.65)
    assert plain == []                  # the 9-pixel core alone is under min_area
    assert len(grown) == 1
    # Grown well beyond the core; smoothing only trims the faint rim's outer
    # pixel, whose 3x3 mean falls below the low level.
    assert grown[0].area == 8 * 28


def test_faint_structure_without_a_bright_core_is_not_a_region():
    normalized = _quiet()
    normalized[5:15, 100:130] = 0.30
    assert reg.find_candidate_regions(normalized, threshold=0.35) == []


def test_regions_are_ordered_largest_first_and_capped():
    normalized = _quiet()
    normalized[0:8, 0:10] = 1.0       # 80 px
    normalized[20:30, 100:130] = 1.0  # 300 px
    normalized[10:18, 300:320] = 1.0  # 160 px
    found = reg.find_candidate_regions(normalized, threshold=0.35, max_candidates=2)
    assert [r.area for r in found] == [300, 160]


def test_min_area_rejects_specks():
    normalized = _quiet()
    normalized[5:8, 5:8] = 1.0
    assert reg.find_candidate_regions(normalized, threshold=0.35, hysteresis=None) == []


def test_non_2d_input_is_rejected():
    with pytest.raises(ValueError):
        reg.find_candidate_regions(np.zeros(10))


def test_adaptive_threshold_only_ever_relaxes_toward_its_floor():
    bright = _quiet()
    bright[0:5, 0:100] = 1.0
    assert reg.resolve_threshold(bright, 0.35) == pytest.approx(0.35)
    faint = np.linspace(0, 0.25, 40 * 600).reshape(40, 600)
    assert 0.15 < reg.resolve_threshold(faint, 0.35) < 0.35
    assert reg.resolve_threshold(_quiet(), 0.35) == pytest.approx(0.15)
    assert reg.resolve_threshold(faint, 0.35, adaptive=False) == 0.35


# ── Display ──────────────────────────────────────────────────────────────────


def _axes(source: str) -> SpectrumAxes:
    return SpectrumAxes(
        time_s=np.arange(3600) * 0.25, freq_mhz=np.linspace(80.0, 45.0, 200), source=source
    )


def test_region_to_axes_reports_mhz_and_seconds_from_a_real_axis():
    region = reg.Region(row0=0, row1=200, col0=400, col1=480, area=500, peak=1.0)
    shown = reg.region_to_axes(region, _axes("axes_table"))
    assert shown["freq_min_mhz"] == pytest.approx(45.0)
    assert shown["freq_max_mhz"] == pytest.approx(80.0)
    assert (shown["start_seconds"], shown["end_seconds"]) == (100, 120)
    assert shown["area"] == 500


def test_header_frequencies_are_not_reported_as_mhz():
    # The CRVAL2/CDELT2 fallback is a channel index on this archive.
    region = reg.Region(row0=0, row1=10, col0=0, col1=4, area=40, peak=1.0)
    shown = reg.region_to_axes(region, _axes("header"))
    assert shown["freq_min_mhz"] is None and shown["freq_max_mhz"] is None
    assert shown["end_seconds"] == 1
