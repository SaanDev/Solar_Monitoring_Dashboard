"""Tests for the Drag-Based Model CME transit math (app.processing.cme_transit)."""
from datetime import datetime, timezone

import pytest

from app.processing.cme_transit import (
    GAMMA_NOMINAL,
    W_DEFAULT,
    _r_of_t,
    arrival_window,
    dbm_arrival,
    is_geoeffective,
)

UTC = timezone.utc
T0 = datetime(2026, 7, 1, 0, 0, tzinfo=UTC)


# ── dbm_arrival ──────────────────────────────────────────────────────────────


def test_r_of_t_is_monotonic_increasing():
    prev = _r_of_t(0.0, 1000.0, W_DEFAULT, GAMMA_NOMINAL, 0.0)
    for t in range(1, 300_000, 5_000):
        r = _r_of_t(float(t), 1000.0, W_DEFAULT, GAMMA_NOMINAL, 0.0)
        assert r > prev
        prev = r


def test_typical_cme_arrives_in_one_to_four_days():
    res = dbm_arrival(1000.0, T0, w_km_s=400.0)
    assert res is not None
    # A ~1000 km/s CME reaches 1 AU in roughly 1.5-3 days.
    assert 24.0 < res["transit_hours"] < 96.0
    assert res["arrival_time"] > T0
    # Drag pulls a fast CME down toward the ambient wind, never below it.
    assert 400.0 <= res["impact_speed_km_s"] <= 1000.0


def test_faster_cme_arrives_sooner():
    fast = dbm_arrival(1500.0, T0, w_km_s=400.0)
    slow = dbm_arrival(800.0, T0, w_km_s=400.0)
    assert fast["arrival_time"] < slow["arrival_time"]


def test_lower_ambient_wind_delays_a_fast_cme():
    # Slower ambient wind => more drag + a lower asymptotic speed => later arrival.
    calm = dbm_arrival(1000.0, T0, w_km_s=250.0)
    brisk = dbm_arrival(1000.0, T0, w_km_s=600.0)
    assert calm["arrival_time"] > brisk["arrival_time"]


def test_slow_cme_is_dragged_up_toward_the_wind():
    # A CME slower than the wind accelerates toward it (impact speed rises).
    res = dbm_arrival(300.0, T0, w_km_s=500.0)
    assert res is not None
    assert 300.0 < res["impact_speed_km_s"] <= 500.0


def test_unusable_inputs_return_none():
    assert dbm_arrival(None, T0) is None
    assert dbm_arrival(0.0, T0) is None
    assert dbm_arrival(-100.0, T0) is None


def test_zero_or_negative_wind_falls_back_to_default():
    # w<=0 must not divide-by-zero or misbehave; it uses the model default.
    assert dbm_arrival(900.0, T0, w_km_s=0.0) == dbm_arrival(900.0, T0, w_km_s=W_DEFAULT)


# ── arrival_window ───────────────────────────────────────────────────────────


def test_arrival_window_brackets_the_nominal():
    win = arrival_window(1000.0, T0, w_km_s=400.0)
    assert win is not None
    assert win["arrival_earliest"] <= win["arrival_time"] <= win["arrival_latest"]
    # The bracket has real width (drag/wind spread produces distinct corners).
    assert win["arrival_earliest"] < win["arrival_latest"]


def test_arrival_window_none_when_unusable():
    assert arrival_window(None, T0) is None


# ── is_geoeffective ──────────────────────────────────────────────────────────


def test_geoeffective_cone_contains_sun_earth_line():
    assert is_geoeffective(0.0, 0.0, 30.0) is True          # dead-on
    assert is_geoeffective(20.0, 10.0, 45.0) is True         # ~22 deg sep < 45
    assert is_geoeffective(90.0, 0.0, 30.0) is False         # limb CME, wide miss


def test_geoeffective_missing_fields_returns_none():
    assert is_geoeffective(None, 0.0, 30.0) is None
    assert is_geoeffective(0.0, None, 30.0) is None
    assert is_geoeffective(0.0, 0.0, None) is None
    assert is_geoeffective(0.0, 0.0, 0.0) is None            # zero width is unusable
