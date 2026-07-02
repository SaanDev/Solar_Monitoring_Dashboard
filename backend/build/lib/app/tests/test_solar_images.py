"""Tests for the solar image catalog and URL construction (network-free)."""
from datetime import datetime, timezone

from app.services.solar_image_service import CATALOG, _with_cache_bust


def test_catalog_has_core_channels():
    ids = {s.id for s in CATALOG}
    assert {"aia171", "aia193", "aia211", "aia304", "hmiic", "hmib", "suvi195"} <= ids


def test_catalog_urls_well_formed():
    for s in CATALOG:
        assert s.thumb_url.startswith("https://")
        assert s.full_url.startswith("https://")
        assert s.label  # human-readable label present


def test_sdo_uses_distinct_thumb_and_full_sizes():
    aia171 = next(s for s in CATALOG if s.id == "aia171")
    assert "512" in aia171.thumb_url
    assert "2048" in aia171.full_url


def test_cache_bust_appends_timestamp():
    ts = datetime(2026, 6, 15, 17, 42, tzinfo=timezone.utc)
    out = _with_cache_bust("https://x/y.jpg", ts)
    assert out == f"https://x/y.jpg?ts={int(ts.timestamp())}"
