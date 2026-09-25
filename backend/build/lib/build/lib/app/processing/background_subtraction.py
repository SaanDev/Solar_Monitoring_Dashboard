"""Background subtraction for dynamic spectra."""
import numpy as np

# CALLISTO log-detector calibration constants.
_DIGIT_FULL_SCALE_MV = 2500.0   # 255 digits == 2500 mV
_DIGITS_MAX = 255.0
_MV_PER_DB = 25.4               # log-amp slope: ~25.4 mV per dB


def row_mean_subtraction(data: np.ndarray) -> np.ndarray:
    """Subtract per-frequency row mean (removes constant RFI and receiver background)."""
    row_means = np.nanmean(data, axis=1, keepdims=True)
    return data - row_means


def digit_to_voltage(digit: np.ndarray) -> np.ndarray:
    """e-CALLISTO digit -> detector voltage [mV] (255 digits = 2500 mV)."""
    return digit * _DIGIT_FULL_SCALE_MV / _DIGITS_MAX


def background_subtract_db(data: np.ndarray) -> np.ndarray:
    """e-CALLISTO background subtraction, returning dB above background.

    digits -> voltage -> dB, then subtract the per-frequency-channel median
    (the quiescent background of each row over time):

        dref = data - min(data)
        dB   = digit_to_voltage(dref) / 25.4
        out  = dB - median(dB, axis=time)
    """
    dref = data - np.nanmin(data)
    dB = digit_to_voltage(dref) / _MV_PER_DB
    dB_median = np.nanmedian(dB, axis=1, keepdims=True)
    return dB - dB_median
