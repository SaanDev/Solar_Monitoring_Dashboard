"""Synthetic e-CALLISTO files and what the CALLISTO Trainer computes for them.

Shared by test_ml_preprocessing.py (inputs, no torch) and test_ml_checkpoints.py
(probabilities, needs torch and the checkpoint). The model only means anything
on inputs built exactly the way its training samples were, and it answers
confidently either way, so a numeric drift in the port would never announce
itself; these pin it.

The golden values were computed by the Trainer itself — ``read_fits_spectrum``,
``normalize_full_spectrum`` + ``crop_from_normalized`` over the whole file,
``row_to_meta_vector`` and the bundle's ``checkpoint.pt`` on CPU — from files
built by :func:`fits_bytes` below. Regenerate them there if a step changes.
"""
from __future__ import annotations

import io

import numpy as np


def synthetic_spectrum(burst: bool = True, n_freq: int = 200, n_time: int = 3600) -> np.ndarray:
    """Deterministic (no RNG) spectrum: a textured background and a burst.

    The burst is a slowly drifting, patchy band (Type II-like) over ~4 minutes,
    with fainter harmonic structure — bright enough over a large enough area that
    the model calls the file a burst.
    """
    rows, cols = np.mgrid[0:n_freq, 0:n_time].astype(np.float64)
    data = 120 + 3.0 * np.sin(rows * 1.7 + cols * 0.13) * np.cos(cols * 0.071 + rows * 0.9)
    if not burst:
        return np.clip(data, 0, 255)
    lane = 40 + (cols - 1200) / 16.0  # drifts ~1 channel every 4 s
    for width, gain, offset in ((22, 45, 0.0), (14, 25, 70.0)):
        band = np.abs(rows - (lane + offset)) < width
        on = band & (cols >= 1200) & (cols < 2200)
        data += np.where(on, gain * (0.7 + 0.3 * np.sin(cols * 0.05 + rows * 0.3)), 0.0)
    return np.clip(data, 0, 255)


def fits_bytes(spectrum: np.ndarray, header: dict, axes: bool) -> bytes:
    """An e-CALLISTO-shaped file: uint8 image, header cards, optional AXES table."""
    from astropy.io import fits

    n_freq, n_time = spectrum.shape
    primary = fits.PrimaryHDU(spectrum.astype(np.uint8))
    for key, value in header.items():
        primary.header[key] = value
    hdus = [primary]
    if axes:
        freq = np.linspace(80.0, 45.0, n_freq)
        time = np.arange(n_time) * 0.25
        hdus.append(fits.BinTableHDU.from_columns(
            [
                fits.Column(name="TIME", format=f"{n_time}D", array=time[np.newaxis]),
                fits.Column(name="FREQUENCY", format=f"{n_freq}D", array=freq[np.newaxis]),
            ],
            name="AXES",
        ))
    buffer = io.BytesIO()
    fits.HDUList(hdus).writeto(buffer)
    return buffer.getvalue()


# Every 32nd pixel of the 224x224 input, row by row: 7 x 7 samples.
_BURST_SAMPLES = [
    0.111111, 0.025338, 0.025338, 0.053416, 0.153998, 0.111111, 0.183615,
    0.025338, 0.106303, 0.134958, 0.164803, 0.096880, 0.048987, 0.037936,
    0.111111, 0.171074, 0.039265, 1.000000, 0.007648, 0.138886, 0.077840,
    0.039569, 0.045585, 0.051102, 0.125535, 1.000000, 0.154190, 0.053801,
    0.125150, 0.082152, 0.177653, 0.097072, 1.000000, 0.024913, 0.086198,
    0.168614, 0.077648, 0.086697, 0.975692, 0.092264, 0.063032, 0.178038,
    0.037369, 0.073742, 0.054185, 0.148633, 0.683063, 0.125150, 0.063406,
]
_QUIET_SAMPLES = [
    0.111111, 0.025338, 0.025338, 0.053416, 0.153998, 0.111111, 0.183615,
    0.068224, 0.149190, 0.177845, 0.207690, 0.139766, 0.091874, 0.073032,
    0.153998, 0.213960, 0.082152, 0.106303, 0.034953, 0.181297, 0.120727,
    0.068224, 0.074240, 0.068032, 0.154190, 0.145485, 0.182846, 0.082456,
    0.125150, 0.082152, 0.177653, 0.097072, 0.101495, 0.024913, 0.086198,
    0.211501, 0.120535, 0.125727, 0.053608, 0.135151, 0.105919, 0.220924,
    0.037369, 0.073742, 0.054185, 0.148633, 0.134087, 0.125150, 0.063406,
]

# filename, header, has AXES table, has a burst, then the Trainer's results:
# metadata, metadata vector, input sum, input samples, burst probability.
CASES = [
    # A trained station, everything from the header and the AXES table.
    dict(
        filename="BIR_20260615_020000_01.fit.gz",
        header={"INSTRUME": "BIR", "DATE-OBS": "2026/06/15", "TIME-OBS": "02:00:00"},
        axes=True, burst=True,
        metadata={"station": "BIR", "date": "2026-06-15", "freq_min_mhz": 45.0,
                  "freq_max_mhz": 80.0, "freq_axis_source": "axes_table"},
        vector=[11, 0.0450000018, 0.0799999982, 0.0350000001, 0.282107651, -0.959382772, 0.800000012],
        input_sum=8843.605435, samples=_BURST_SAMPLES, probability=0.9956043,
    ),
    # A station outside the vocabulary (index 0) without an AXES table: the
    # header's placeholder frequencies, and the date from the filename.
    dict(
        filename="INDIA-OOTY_20251231_234500_59.fit.gz",
        header={"INSTRUME": "INDIA-OOTY", "CRVAL2": 200.0, "CDELT2": -1.0},
        axes=False, burst=True,
        metadata={"station": "INDIA-OOTY", "date": "2025-12-31", "freq_min_mhz": 1.0,
                  "freq_max_mhz": 200.0, "freq_axis_source": "header"},
        vector=[0, 0.00100000005, 0.200000003, 0.199000001, -0.00430059293, 0.999990761, 0.75],
        input_sum=8843.605435, samples=_BURST_SAMPLES, probability=0.9924898,
    ),
    # No INSTRUME card: the station comes from the filename.
    dict(
        filename="ALASKA-COHOE_20260301_101500_62.fit.gz",
        header={},
        axes=True, burst=True,
        metadata={"station": "ALASKA-COHOE", "date": "2026-03-01", "freq_min_mhz": 45.0,
                  "freq_max_mhz": 80.0, "freq_axis_source": "axes_table"},
        vector=[2, 0.0450000018, 0.0799999982, 0.0350000001, 0.858401537, 0.512978375, 0.800000012],
        input_sum=8843.605435, samples=_BURST_SAMPLES, probability=0.9952267,
    ),
    # The first station's next segment, quiet.
    dict(
        filename="BIR_20260615_021500_01.fit.gz",
        header={"INSTRUME": "BIR", "DATE-OBS": "2026/06/15", "TIME-OBS": "02:15:00"},
        axes=True, burst=False,
        metadata={"station": "BIR", "date": "2026-06-15", "freq_min_mhz": 45.0,
                  "freq_max_mhz": 80.0, "freq_axis_source": "axes_table"},
        vector=[11, 0.0450000018, 0.0799999982, 0.0350000001, 0.282107651, -0.959382772, 0.800000012],
        input_sum=5575.646210, samples=_QUIET_SAMPLES, probability=0.0548886,
    ),
]


def case_bytes(case: dict) -> bytes:
    return fits_bytes(synthetic_spectrum(case["burst"]), case["header"], case["axes"])
