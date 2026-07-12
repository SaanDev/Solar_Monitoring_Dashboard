"""Tests for Type II shock-parameter estimation (Path A) and the .efaproj round-trip.

Covers the ported math (power-law fit recovery, Newkirk shock speed/height verified by
independent recomputation of the frozen formulas) and the desktop-compatible project
payload (meta["analysis_session"] + analysis_* arrays).
"""
import io

import numpy as np
import pytest

from app.processing import analysis_session as asx
from app.processing import efaproj
from app.processing.shock_analysis import (
    _SHOCK_SPEED_CONST,
    compute_shock_parameters,
    extract_max_intensity,
    power_law_fit,
)


# ── Power-law fit ────────────────────────────────────────────────────────────


def test_power_law_fit_recovers_parameters():
    a_true, b_true = 215.0, 0.62
    t = np.linspace(1.0, 90.0, 150)
    f = a_true * t ** (-b_true)
    fit = power_law_fit(t, f)
    assert fit["a"] == pytest.approx(a_true, rel=1e-4)
    assert fit["b"] == pytest.approx(b_true, rel=1e-4)
    assert fit["r2"] == pytest.approx(1.0, abs=1e-6)
    assert fit["rmse"] == pytest.approx(0.0, abs=1e-4)
    assert fit["point_count"] == 150


def test_power_law_fit_needs_two_positive_points():
    with pytest.raises(ValueError):
        power_law_fit([0.0], [100.0])


# ── Newkirk shock parameters ─────────────────────────────────────────────────


@pytest.mark.parametrize("fold,harmonic", [(1, False), (2, False), (3, True), (4, True)])
def test_shock_parameters_match_newkirk_formulas(fold, harmonic):
    """Recompute the frozen Newkirk formulas independently and compare to the output."""
    a, b = 200.0, 0.5
    t = np.linspace(1.0, 80.0, 120)
    f = a * t ** (-b)
    fit = power_law_fit(t, f)
    res = compute_shock_parameters(fit, t, f, fold=fold, harmonic=harmonic)
    curves = res["curves"]
    fit_line = res["fit_line"]

    denom = fold * 3.385
    hn = 2.0 if harmonic else 1.0
    tt = np.asarray(fit_line["time_s"])
    # Independent drift + Newkirk recomputation (mirrors the source constants).
    drift = -fit["a"] * fit["b"] * tt ** (-fit["b"] - 1)
    shock_freq = np.asarray(fit_line["freq_mhz"]) / hn
    shock_drift = drift / hn
    g = np.log(shock_freq ** 2 / denom)
    exp_speed = (_SHOCK_SPEED_CONST * np.abs(shock_drift)) / (shock_freq * g ** 2)
    exp_height = 4.32 * np.log(10) / g

    np.testing.assert_allclose(curves["shock_freq_mhz"], shock_freq, rtol=1e-9)
    np.testing.assert_allclose(curves["shock_speed_km_s"], exp_speed, rtol=1e-9)
    np.testing.assert_allclose(curves["shock_height_rs"], exp_height, rtol=1e-9)

    s = res["shock_summary"]
    assert s["fold"] == fold
    assert s["harmonic"] is harmonic
    assert s["harmonic_number"] == int(hn)
    # Positive, finite, and consistent averages.
    assert s["initial_shock_speed_km_s"] > 0
    assert s["avg_shock_height_rs"] == pytest.approx(float(np.mean(exp_height)), rel=1e-9)


def test_harmonic_halves_effective_frequency():
    a, b = 180.0, 0.55
    t = np.linspace(1.0, 60.0, 100)
    f = a * t ** (-b)
    fit = power_law_fit(t, f)
    fund = compute_shock_parameters(fit, t, f, fold=1, harmonic=False)
    harm = compute_shock_parameters(fit, t, f, fold=1, harmonic=True)
    # Harmonic emission maps to half the plasma frequency.
    assert harm["curves"]["shock_freq_mhz"][0] == pytest.approx(
        fund["curves"]["shock_freq_mhz"][0] / 2.0, rel=1e-9
    )


# ── Maximum-intensity extraction ─────────────────────────────────────────────


def _synthetic_spectrogram():
    nf, nt = 220, 100
    freqs = np.linspace(400.0, 20.0, nf)  # high → low (e-CALLISTO order)
    tax = np.arange(nt) * 0.25
    rng = np.random.RandomState(0)
    arr = rng.normal(0.0, 0.15, (nf, nt))
    ridge = 180.0 * np.clip(tax, 0.25, None) ** (-0.4)
    for j in range(nt):
        i = int(np.argmin(np.abs(freqs - ridge[j])))
        arr[i, j] += 9.0
    return arr, tax, freqs, ridge


def test_extract_max_intensity_follows_ridge():
    arr, tax, freqs, ridge = _synthetic_spectrogram()
    res = extract_max_intensity(arr, tax, freqs, polygon=None, auto_clean=False)
    assert len(res["freqs"]) == len(tax)
    # Recovered peak frequencies track the injected ridge (within one channel step).
    err = np.abs(np.asarray(res["freqs"]) - ridge)
    assert np.median(err) < 5.0


def test_burst_polygon_isolates_region():
    arr, tax, freqs, _ridge = _synthetic_spectrogram()
    # A polygon covering only the first half of the burst in time.
    poly = [[0.0, 20.0], [0.0, 400.0], [12.5, 400.0], [12.5, 20.0]]
    res = extract_max_intensity(arr, tax, freqs, polygon=poly, auto_clean=True)
    assert len(res["freqs"]) > 0
    # All surviving columns fall inside the selected time window.
    assert max(res["time_seconds"]) <= 12.5 + 1e-6


# ── .efaproj round-trip (desktop compatibility) ──────────────────────────────


def test_efaproj_analysis_session_round_trips():
    a, b = 210.0, 0.5
    t = np.linspace(1.0, 60.0, 80)
    f = a * t ** (-b)
    fit = power_law_fit(t, f)
    summary = compute_shock_parameters(fit, t, f, fold=2, harmonic=False)["shock_summary"]

    session = {
        "source": {"filename": "TEST", "shape": [100, 80]},
        "max_intensity": {
            "time_channels": list(range(80)),
            "time_seconds": t.tolist(),
            "freqs": f.tolist(),
            "fundamental": True,
            "harmonic": False,
        },
        "analyzer": {"fit_params": fit, "fold": 2, "shock_summary": summary},
    }
    meta_session, arrays = asx.to_project_payload(session)
    assert meta_session is not None

    meta = {"filename": "TEST", "analysis_session": meta_session}
    buf = io.BytesIO()
    efaproj.write_project(buf, meta=meta, arrays=arrays)

    payload = efaproj.read_project(io.BytesIO(buf.getvalue()))
    assert "analysis_session" in payload.meta
    for key in ("analysis_time_channels", "analysis_time_seconds", "analysis_freqs"):
        assert key in payload.arrays

    # Re-attach arrays and normalize (mirrors open_project / the desktop loader).
    sp = dict(payload.meta["analysis_session"])
    mb = dict(sp["max_intensity"])
    mb["time_channels"] = payload.arrays["analysis_time_channels"]
    mb["time_seconds"] = payload.arrays["analysis_time_seconds"]
    mb["freqs"] = payload.arrays["analysis_freqs"]
    sp["max_intensity"] = mb
    norm = asx.normalize_session(sp)
    assert norm is not None

    np.testing.assert_allclose(norm["max_intensity"]["freqs"], f, rtol=1e-6)
    assert norm["analyzer"]["fold"] == 2
    assert norm["analyzer"]["shock_summary"]["initial_shock_speed_km_s"] == pytest.approx(
        summary["initial_shock_speed_km_s"], rel=1e-9
    )
    ok, _reason = asx.validate_session_for_source(norm, current_shape=[100, 80])
    assert ok
