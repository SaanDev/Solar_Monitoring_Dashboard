"""Tabular metadata features for the multi-input burst classifier.

Ported from Burst Identifier src/data/metadata_features.py — pure Python/NumPy,
no PyTorch or model dependencies.

Feature vector layout:
  [station_index, freq_min/1000, freq_max/1000, freq_span/1000,
   doy_sin, doy_cos, year_norm]

station_index is an integer id from the checkpoint's vocab (0 = unknown).
Frequency features are normalised to GHz-ish scale (MHz / 1000) so they
sit near O(1). Date is encoded as cyclical day-of-year (sin/cos, generalises
across years) plus a normalised year.
"""
from __future__ import annotations

import math
from datetime import date as _date
from typing import Any, Mapping

import numpy as np

NUMERIC_FEATURES = ("freq_min", "freq_max", "freq_span", "doy_sin", "doy_cos", "year")
NUM_NUMERIC = len(NUMERIC_FEATURES)
META_VECTOR_LEN = 1 + NUM_NUMERIC  # station index + 6 numerics

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
    """Return (sin doy, cos doy, normalised year); zeros when unparseable."""
    text = str(value or "").strip()
    parts = text.split("-")
    if len(parts) < 3:
        return 0.0, 0.0, 0.0
    try:
        year, month, day = int(parts[0]), int(parts[1]), int(parts[2][:2])
        doy = _date(year, month, day).timetuple().tm_yday
    except (ValueError, TypeError):
        return 0.0, 0.0, 0.0
    angle = 2.0 * math.pi * doy / 365.25
    return math.sin(angle), math.cos(angle), (year - _YEAR_REF) / _YEAR_SCALE


def row_to_meta_vector(row: Mapping[str, Any], vocab: Mapping[str, int]) -> np.ndarray:
    """Build the [station_idx, numeric...] float32 vector for one file's metadata."""
    station_idx = float(vocab.get(_clean_station(row.get("station")), 0))

    freq_min = _safe_float(row.get("freq_min_mhz")) or 0.0
    freq_max = _safe_float(row.get("freq_max_mhz")) or 0.0
    freq_span = abs(freq_max - freq_min)

    doy_sin, doy_cos, year_norm = _date_features(row.get("date"))

    return np.array(
        [
            station_idx,
            freq_min / FREQ_REF_MHZ,
            freq_max / FREQ_REF_MHZ,
            freq_span / FREQ_REF_MHZ,
            doy_sin,
            doy_cos,
            year_norm,
        ],
        dtype=np.float32,
    )
