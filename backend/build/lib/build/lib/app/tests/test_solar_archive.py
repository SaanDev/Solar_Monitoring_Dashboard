"""Tests for the Helioviewer-backed solar image archive."""
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

import app.api.routes_solar_images as routes
import app.services.solar_archive_service as sa
from app.main import app

_DATE = "2025-01-15"


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


# ── URL building (no network) ──


def test_image_scale_per_instrument():
    assert sa._image_scale(1250) == pytest.approx(2.4414, abs=1e-3)   # disk
    assert sa._image_scale(30000) == pytest.approx(58.59, abs=1e-2)   # LASCO C3


def test_screenshot_url_overlays_noaa_active_regions_on_disk():
    url = sa.screenshot_url(sa._BY_ID["aia171"], "2025-01-15T12:00:00Z", with_events=True)
    assert "/v2/takeScreenshot/" in url
    assert "events=%5BAR,NOAA_SWPC_Observer,1%5D" in url
    assert "eventLabels=true" in url


def test_screenshot_url_no_overlay_for_coronagraph():
    # LASCO does not support on-disk active-region overlays.
    url = sa.screenshot_url(sa._BY_ID["lascoc2"], "2025-01-15T12:00:00Z", with_events=True)
    assert "NOAA_SWPC_Observer" not in url
    assert "events=&" in url or url.endswith("events=") or "events=&eventLabels=false" in url


# ── List endpoint (closest-time mocked) ──


async def test_archive_images_list(client):
    fixed = datetime(2025, 1, 15, 11, 59, 45, tzinfo=timezone.utc)
    with patch.object(sa, "_closest_time", new=AsyncMock(return_value=fixed)):
        r = await client.get(f"/api/solar/archive/images?date={_DATE}&events=true")
    assert r.status_code == 200
    body = r.json()
    assert body["with_events"] is True
    assert len(body["images"]) == len(sa.CATALOG)

    by_id = {im["id"]: im for im in body["images"]}
    aia = by_id["aia171"]
    assert "NOAA_SWPC_Observer" in aia["image_url"]
    assert aia["png_download_url"].startswith("/api/solar/archive/image?")
    assert aia["jp2_download_url"].startswith("/api/solar/archive/jp2?")
    assert aia["time"] is not None
    # Coronagraph keeps no AR overlay even with events on.
    assert "NOAA_SWPC_Observer" not in by_id["lascoc2"]["image_url"]


_DATED_BROWSE = """
20260630_195022_2048_0171.jpg
20260630_200522_2048_0171.jpg
20260630_201022_2048_0171.jpg
20260630_200000_2048_HMIB.jpg
20260630_200000_2048_HMIBC.jpg
20260630_200000_2048_HMIIC.jpg
"""


async def test_historical_uses_sdo_dated_browse_not_helioviewer(client):
    # The reported bug: browsing 2026-06-30 20:00 returned a 2026-06-29 Helioviewer
    # frame. It must now return a real 2026-06-30 frame from SDO's dated archive,
    # nearest the requested time, with downloads targeting that shown frame.
    stale = datetime(2026, 6, 29, 20, 0, tzinfo=timezone.utc)  # Helioviewer lag
    with patch.object(sa, "_cached_listing", new=AsyncMock(return_value=_DATED_BROWSE)), patch.object(
        sa, "_closest_time", new=AsyncMock(return_value=stale)
    ):
        r = await client.get("/api/solar/archive/images?date=2026-06-30&time=20:00")
    assert r.status_code == 200
    by = {i["id"]: i for i in r.json()["images"]}

    aia = by["aia171"]
    assert aia["image_url"].startswith("https://sdo.gsfc.nasa.gov/assets/img/browse/2026/06/30/")
    assert "20260630_200522_2048_0171.jpg" in aia["image_url"]  # nearest to 20:00
    assert aia["time"].startswith("2026-06-30T20:05")           # real frame time, not 06-29
    assert "date=2026-06-30" in aia["png_download_url"]          # download = shown frame
    assert "helioviewer" not in aia["image_url"]
    # Code match is exact: HMIB must not pick up HMIBC.
    assert "20260630_200000_2048_HMIB.jpg" in by["hmib"]["image_url"]
    # LASCO has no dated archive -> Helioviewer nearest, still labelled its real time.
    assert "helioviewer" in by["lascoc2"]["image_url"]


async def test_historical_overlay_falls_back_to_helioviewer(client):
    # With the active-region overlay on, browse frames can't carry it, so the disk
    # images come from Helioviewer (which supports the HEK overlay) instead.
    fixed = datetime(2026, 6, 30, 20, 0, tzinfo=timezone.utc)
    with patch.object(sa, "_closest_time", new=AsyncMock(return_value=fixed)):
        r = await client.get("/api/solar/archive/images?date=2026-06-30&time=20:00&events=true")
    assert r.status_code == 200
    by = {i["id"]: i for i in r.json()["images"]}
    assert "NOAA_SWPC_Observer" in by["aia171"]["image_url"]


async def test_latest_mode_shows_browse_frames_with_science_downloads(client):
    # Latest mode displays the fresh near-real-time browse frame (as the Overview
    # does) while downloads still resolve to the newest *science* frame.
    sci = datetime(2026, 6, 29, 20, 30, tzinfo=timezone.utc)     # days-old science
    browse = datetime(2026, 7, 1, 15, 50, tzinfo=timezone.utc)   # fresh quick-look
    with patch.object(sa, "_closest_time", new=AsyncMock(return_value=sci)), patch.object(
        sa, "_browse_time", new=AsyncMock(return_value=browse)
    ):
        r = await client.get("/api/solar/archive/images?date=2026-07-01&latest=true")
    assert r.status_code == 200
    body = r.json()
    assert body["latest"] is True
    by_id = {im["id"]: im for im in body["images"]}

    aia = by_id["aia171"]
    assert aia["image_url"].startswith("https://sdo.gsfc.nasa.gov/assets/img/latest/")
    assert "helioviewer" not in aia["image_url"]
    assert aia["time"].startswith("2026-07-01")                 # fresh browse time
    assert "date=2026-06-29" in aia["png_download_url"]          # download = science frame
    assert "date=2026-06-29" in aia["fts_download_url"]
    # Coronagraph uses the SOHO realtime browse frame.
    assert by_id["lascoc2"]["image_url"].startswith("https://soho.nascom.nasa.gov/data/realtime/c2/")


# ── Download proxies ──


async def test_archive_image_download_attachment(client):
    with patch.object(routes, "fetch_screenshot_png", new=AsyncMock(return_value=b"\x89PNGdata")):
        r = await client.get(
            f"/api/solar/archive/image?date={_DATE}&id=aia171&events=true&download=1"
        )
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/png"
    assert "attachment" in r.headers["content-disposition"]
    assert "_AR.png" in r.headers["content-disposition"]


async def test_archive_image_inline_when_not_download(client):
    with patch.object(routes, "fetch_screenshot_png", new=AsyncMock(return_value=b"\x89PNG")):
        r = await client.get(f"/api/solar/archive/image?date={_DATE}&id=aia171")
    assert r.status_code == 200
    assert "attachment" not in r.headers.get("content-disposition", "")


async def test_archive_jp2_download(client):
    with patch.object(
        routes, "fetch_jp2", new=AsyncMock(return_value=(b"JP2DATA", "aia171_2025-01-15_1200.jp2"))
    ):
        r = await client.get(f"/api/solar/archive/jp2?date={_DATE}&id=aia171&download=1")
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/jp2"
    assert 'filename="aia171_2025-01-15_1200.jp2"' in r.headers["content-disposition"]


async def test_archive_image_unknown_id_404(client):
    # Unknown id returns before any network call.
    r = await client.get(f"/api/solar/archive/image?date={_DATE}&id=nope")
    assert r.status_code == 404


async def test_archive_bad_date_400(client):
    r = await client.get("/api/solar/archive/images?date=2025/01/15")
    assert r.status_code == 400


# ── Raw FITS (AIA + HMI synoptic) ──

_AIA_LISTING = """
AIA20250115_1158_0171.fits
AIA20250115_1200_0171.fits
AIA20250115_1202_0171.fits
AIA20250115_1200_0094.fits
"""

_HMI_LISTING = """
hmi.M_720s.20250115_120000_TAI.fits
hmi.Ic_720s.20250115_120000_TAI.fits
hmi.M_720s.20250115_130000_TAI.fits
"""


# One SDO dated-browse frame per catalog code (historical display source).
_SDO_BROWSE_LISTING = " ".join(
    f"20250115_120000_2048_{c}.jpg"
    for c in ("0094", "0131", "0171", "0193", "0211", "0304", "0335", "1600", "HMIIC", "HMIB")
)


async def test_list_marks_fits_availability(client):
    fixed = datetime(2025, 1, 15, 12, 0, tzinfo=timezone.utc)
    with patch.object(sa, "_closest_time", new=AsyncMock(return_value=fixed)), patch.object(
        sa, "_cached_listing", new=AsyncMock(return_value=_SDO_BROWSE_LISTING)
    ):
        r = await client.get(f"/api/solar/archive/images?date={_DATE}")
    by_id = {im["id"]: im for im in r.json()["images"]}
    assert by_id["aia171"]["fits_available"] is True
    assert by_id["aia171"]["fts_download_url"].startswith("/api/solar/archive/fits?")
    assert by_id["hmib"]["fits_available"] is True          # magnetogram has FITS
    assert by_id["hmic"]["fits_available"] is False          # continuum: not in archive
    assert by_id["lascoc2"]["fits_available"] is False
    assert by_id["lascoc2"]["fts_download_url"] is None


async def test_resolve_aia_fits_picks_nearest_for_wave():
    dt = datetime(2025, 1, 15, 12, 1, tzinfo=timezone.utc)
    with patch.object(sa, "_listing", new=AsyncMock(return_value=_AIA_LISTING)):
        url, fname = await sa._resolve_fits(None, sa._BY_ID["aia171"], dt)
    assert fname == "AIA20250115_1200_0171.fits"  # nearest 0171, not the 0094
    assert url.endswith("/H1200/AIA20250115_1200_0171.fits")


async def test_resolve_hmi_fits_filters_series_and_picks_nearest():
    # hmib selects M_720s only (ignores the Ic_720s entry) and picks the nearest.
    with patch.object(sa, "_listing", new=AsyncMock(return_value=_HMI_LISTING)):
        _, mag = await sa._resolve_fits(
            None, sa._BY_ID["hmib"], datetime(2025, 1, 15, 12, 40, tzinfo=timezone.utc)
        )
    assert mag == "hmi.M_720s.20250115_130000_TAI.fits"  # 13:00 is nearer to 12:40


async def test_fits_endpoint_download(client):
    with patch.object(
        routes, "fetch_fts", new=AsyncMock(return_value=(b"SIMPLE  = T", "AIA20250115_1200_0171.fits"))
    ):
        r = await client.get(f"/api/solar/archive/fits?date={_DATE}&id=aia171&download=1")
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/fits"
    assert 'filename="AIA20250115_1200_0171.fits"' in r.headers["content-disposition"]


async def test_fits_endpoint_404_for_lasco(client):
    # LASCO has no FITS provider -> fetch_fts returns None before any network call.
    r = await client.get(f"/api/solar/archive/fits?date={_DATE}&id=lascoc2")
    assert r.status_code == 404
