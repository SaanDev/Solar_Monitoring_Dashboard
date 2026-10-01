"""The metadata vector BnB v1.0's metadata branch takes alongside the image.

Ported from the CALLISTO Trainer (``core/metadata_features.py``,
``row_to_meta_vector``) with the numerics unchanged:

``[station_index, freq_min, freq_max, freq_span, doy_sin, doy_cos, year]``

* ``station_index`` — the station's index in the checkpoint's vocabulary, 0 for
  any station not in it. The name is matched exactly as the FITS ``INSTRUME``
  header (or the filename) writes it, only trimmed: that is how training built
  the vocabulary.
* frequencies in MHz / 1000, so they sit near O(1).
* the date as a point on the yearly cycle plus ``(year - 2010) / 20``.

Index 0 was never used in training, but measured on 7,883 held-out files the
station input moves a file's probability by about 0.01 on average, so an unseen
station is scored like any other (see the registry for the measurements).
"""
from __future__ import annotations

import math
from datetime import date as _date
from typing import Any, Mapping

import numpy as np

NUMERIC_FEATURES = ("freq_min", "freq_max", "freq_span", "doy_sin", "doy_cos", "year")
NUM_NUMERIC = len(NUMERIC_FEATURES)
META_VECTOR_LEN = 1 + NUM_NUMERIC
FREQ_REF_MHZ = 1000.0
_YEAR_REF = 2010.0
_YEAR_SCALE = 20.0


def _clean_station(value: Any) -> str:
    return str(value or "").strip()


def _safe_float(value: Any) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def _date_features(value: Any) -> tuple[float, float, float]:
    """``(sin doy, cos doy, normalised year)``; zeros when unparseable."""
    parts = str(value or "").strip().split("-")
    if len(parts) < 3:
        return 0.0, 0.0, 0.0
    try:
        year, month, day = int(parts[0]), int(parts[1]), int(parts[2][:2])
        doy = _date(year, month, day).timetuple().tm_yday
    except (ValueError, TypeError):
        return 0.0, 0.0, 0.0
    angle = 2.0 * math.pi * doy / 365.25
    return math.sin(angle), math.cos(angle), (year - _YEAR_REF) / _YEAR_SCALE


def station_index(station: Any, vocab: Mapping[str, int]) -> int:
    """The station's vocabulary index, 0 when it is not in the vocabulary."""
    return int(vocab.get(_clean_station(station), 0))


def meta_vector(metadata: Mapping[str, Any], vocab: Mapping[str, int]) -> np.ndarray:
    """The float32 metadata vector for one file's metadata dict."""
    freq_min = _safe_float(metadata.get("freq_min_mhz"))
    freq_max = _safe_float(metadata.get("freq_max_mhz"))
    freq_min = 0.0 if freq_min is None else freq_min
    freq_max = 0.0 if freq_max is None else freq_max
    doy_sin, doy_cos, year = _date_features(metadata.get("date"))
    return np.array(
        [
            float(station_index(metadata.get("station"), vocab)),
            freq_min / FREQ_REF_MHZ,
            freq_max / FREQ_REF_MHZ,
            abs(freq_max - freq_min) / FREQ_REF_MHZ,
            doy_sin,
            doy_cos,
            year,
        ],
        dtype=np.float32,
    )
