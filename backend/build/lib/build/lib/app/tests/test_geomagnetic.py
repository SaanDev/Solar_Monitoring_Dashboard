"""Tests for Kp / Dst parsing and storm-scale classification."""
from app.collectors.collect_kp import parse_kp
from app.collectors.collect_dst import parse_dst
from app.processing.geomag_scale import kp_storm_scale, dst_storm_level


def test_parse_kp_dict_format():
    raw = [
        {"time_tag": "2026-06-15T09:00:00", "Kp": 2.33, "a_running": 9, "station_count": 8},
        {"time_tag": "2026-06-15T12:00:00", "Kp": 1.0, "a_running": 4, "station_count": 8},
    ]
    rows = parse_kp(raw)
    assert len(rows) == 2
    assert rows[1]["kp"] == 1.0
    assert rows[0]["time"].tzinfo is not None  # UTC-aware


def test_parse_dst_wdc_format():
    # One day, 24 hourly values + daily mean, plus a missing-value example.
    line = (
        "DST2606*01RRX020   0 -20 -20 -21 -23 -20 -16 -16 -15 "
        "-13 -14 -13 -13 -17 -22 -28 -30 -31 -36 -33 -36 -39 -43 -45 -41 -25"
    )
    rows = parse_dst(line)
    assert len(rows) == 24
    assert rows[0]["time"].hour == 0
    assert rows[0]["dst"] == -20.0
    assert rows[23]["dst"] == -41.0  # last hourly, not the daily mean


def test_parse_dst_skips_missing():
    line = "DST2606*02RRX020   0 9999 9999 -10" + " 0" * 21 + " -5"
    rows = parse_dst(line)
    # First two hours are missing (9999) and dropped.
    assert all(r["dst"] != 9999 for r in rows)
    assert rows[0]["time"].hour == 2


def test_kp_g_scale():
    assert kp_storm_scale(1.0) is None
    assert kp_storm_scale(5.0) == "G1"
    assert kp_storm_scale(6.0) == "G2"
    assert kp_storm_scale(7.0) == "G3"
    assert kp_storm_scale(8.0) == "G4"
    assert kp_storm_scale(9.0) == "G5"


def test_dst_storm_level():
    assert dst_storm_level(-10.0) is None
    assert dst_storm_level(-40.0) == "Weak storm"
    assert dst_storm_level(-75.0) == "Moderate storm"
    assert dst_storm_level(-150.0) == "Intense storm"
    assert dst_storm_level(-300.0) == "Super storm"
