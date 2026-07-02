"""Tests for e-CALLISTO processing using a synthetic FITS file."""
import tempfile
from pathlib import Path
import numpy as np
import pytest
from astropy.io import fits

from app.processing.fits_loader import load_ecallisto_fits
from app.processing.background_subtraction import row_mean_subtraction
from app.processing.rfi_cleaning import percentile_clip, normalize
from app.processing.burst_detection import detect_bursts


@pytest.fixture
def synthetic_fits(tmp_path: Path) -> Path:
    """Create a minimal e-CALLISTO-style FITS file."""
    n_freq, n_time = 200, 3600
    rng = np.random.default_rng(42)
    data = rng.uniform(60, 100, size=(n_freq, n_time)).astype(np.float32)
    # Inject a burst-like feature strong enough to survive row-mean subtraction
    # The burst spans only ~1% of the time axis so row mean is mostly background
    data[50:80, 300:340] += 200

    time_arr = np.linspace(0, 900, n_time)
    freq_arr = np.linspace(870, 45, n_freq)

    primary = fits.PrimaryHDU(data)
    # e-CALLISTO uses 'YYYY/MM/DD' DATE-OBS + separate TIME-OBS.
    primary.header["DATE-OBS"] = "2024/01/15"
    primary.header["TIME-OBS"] = "10:00:00.000"
    primary.header["FRQMIN"] = 45.0
    primary.header["FRQMAX"] = 870.0

    # Real e-CALLISTO stores TIME/FREQUENCY as single-row array columns.
    time_col = fits.Column(name="TIME", format=f"{n_time}E", array=time_arr.reshape(1, n_time))
    freq_col = fits.Column(name="FREQUENCY", format=f"{n_freq}E", array=freq_arr.reshape(1, n_freq))
    bin_table = fits.BinTableHDU.from_columns([time_col, freq_col])

    hdul = fits.HDUList([primary, bin_table])
    path = tmp_path / "test_spectrum.fits"
    hdul.writeto(path)
    return path


def test_fits_loader(synthetic_fits):
    fd = load_ecallisto_fits(synthetic_fits)
    assert fd.data.shape == (200, 3600)
    assert len(fd.time_axis) == 3600   # single-row TIME array, raveled
    assert len(fd.freq_axis) == 200    # single-row FREQUENCY array, raveled


def test_pipeline(synthetic_fits):
    fd = load_ecallisto_fits(synthetic_fits)
    cleaned = row_mean_subtraction(fd.data)
    clipped = percentile_clip(cleaned)
    normed = normalize(clipped)
    assert normed.min() >= 0.0
    assert normed.max() <= 1.0


def test_burst_detection(synthetic_fits):
    fd = load_ecallisto_fits(synthetic_fits)
    freq_axis = np.linspace(870, 45, 200)
    # Detect on background-subtracted data before normalization so the injected
    # burst remains well above the background noise level
    cleaned = row_mean_subtraction(fd.data)
    bursts = detect_bursts(cleaned, fd.time_axis, freq_axis, threshold_sigma=2.5, min_pixels=10)
    assert len(bursts) >= 1, "Expected at least one burst candidate"
    assert bursts[0].t_end_s > bursts[0].t_start_s
