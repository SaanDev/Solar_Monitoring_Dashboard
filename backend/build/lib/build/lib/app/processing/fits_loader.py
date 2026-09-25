"""Load e-CALLISTO FITS files using Astropy."""
from pathlib import Path
import numpy as np
from astropy.io import fits


class FitsData:
    def __init__(
        self,
        data: np.ndarray,
        time_axis: np.ndarray,
        freq_axis: np.ndarray,
        header: dict,
    ):
        self.data = data          # shape (n_freq, n_time)
        self.time_axis = time_axis  # seconds since obs start
        self.freq_axis = freq_axis  # MHz
        self.header = header


def load_ecallisto_fits(path: Path) -> FitsData:
    with fits.open(path) as hdul:
        primary = hdul[0]
        header = dict(primary.header)
        data = primary.data.astype(np.float32)

        # Time/frequency axes: e-CALLISTO stores them as single-row array
        # columns in extension 1 (shape (1, N)), so ravel to 1-D.
        if len(hdul) > 1 and hdul[1].data is not None:
            col_names = [c.name.upper() for c in hdul[1].columns]
            if "TIME" in col_names:
                time_axis = np.asarray(hdul[1].data["TIME"], dtype=np.float64).ravel()
            else:
                time_axis = np.arange(data.shape[1], dtype=np.float64)

            if "FREQUENCY" in col_names:
                freq_axis = np.asarray(hdul[1].data["FREQUENCY"], dtype=np.float64).ravel()
            else:
                freq_axis = _freq_from_header(header, data.shape[0])
        else:
            time_axis = np.arange(data.shape[1], dtype=np.float64)
            freq_axis = _freq_from_header(header, data.shape[0])

    # Guard against axis/data length mismatches (truncated or padded files).
    if time_axis.shape[0] != data.shape[1]:
        time_axis = np.arange(data.shape[1], dtype=np.float64)
    if freq_axis.shape[0] != data.shape[0]:
        freq_axis = _freq_from_header(header, data.shape[0])

    return FitsData(data=data, time_axis=time_axis, freq_axis=freq_axis, header=header)


def _freq_from_header(header: dict, n_freq: int) -> np.ndarray:
    f_start = float(header.get("FRQMIN", header.get("FREQ_MIN", 45.0)))
    f_stop = float(header.get("FRQMAX", header.get("FREQ_MAX", 870.0)))
    return np.linspace(f_start, f_stop, n_freq)
