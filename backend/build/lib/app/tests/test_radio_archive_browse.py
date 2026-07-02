"""Tests for the e-CALLISTO archive browse endpoints (by date + station)."""
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

import app.services.ecallisto_service as svc
from app.collectors.collect_ecallisto import FitsFile
from app.config import settings
from app.main import app

_DATE = "2026-06-15"


def _fits(station: str, hms: str) -> FitsFile:
    start = datetime.strptime("20260615" + hms, "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)
    fname = f"{station}_20260615_{hms}_59.fit.gz"
    return FitsFile(station=station, start=start, filename=fname, url="http://x/" + fname)


_DAY_FILES = [
    _fits("SRI-Lanka", "050000"),
    _fits("SRI-Lanka", "051500"),
    _fits("HUMAIN", "050000"),
]

_META = {
    "station": "SRI-Lanka",
    "start_time": datetime(2026, 6, 15, 5, 0, tzinfo=timezone.utc),
    "end_time": datetime(2026, 6, 15, 5, 15, tzinfo=timezone.utc),
    "freq_min_mhz": 45.0,
    "freq_max_mhz": 84.5,
    "image_filename": "SRI-Lanka_20260615_051500_v3.png",
    "processing_method": "bg-subtracted",
}

_BURST_TEXT = """Product summary header line
20260615   05:00-05:10   III   SRI-Lanka,HUMAIN
20260615   06:00-06:05   II   ALASKA-COHOE
20260614   01:00-01:05   III   HUMAIN
"""


@pytest.fixture(autouse=True)
def _clear_caches():
    svc._resolved_by_date.clear()
    yield


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


async def test_archive_stations(client):
    with patch.object(svc, "list_day_files", new=AsyncMock(return_value=_DAY_FILES)):
        r = await client.get(f"/api/radio/archive/stations?date={_DATE}")
    assert r.status_code == 200
    body = r.json()
    ids = {s["id"]: s["has_metadata"] for s in body["stations"]}
    assert set(ids) == {"SRI-Lanka", "HUMAIN"}
    assert ids["SRI-Lanka"] is True  # in the known catalog


async def test_archive_files_sorted_for_station(client):
    with patch.object(svc, "list_day_files", new=AsyncMock(return_value=_DAY_FILES)):
        r = await client.get(f"/api/radio/archive/files?date={_DATE}&station=SRI-Lanka")
    assert r.status_code == 200
    files = r.json()["files"]
    assert [f["filename"] for f in files] == [
        "SRI-Lanka_20260615_050000_59.fit.gz",
        "SRI-Lanka_20260615_051500_59.fit.gz",
    ]


async def test_archive_spectrum_defaults_to_latest_segment(client):
    with patch.object(svc, "list_day_files", new=AsyncMock(return_value=_DAY_FILES)), patch.object(
        svc, "_render_archive_file", new=AsyncMock(return_value=_META)
    ) as render:
        r = await client.get(f"/api/radio/archive/spectrum?date={_DATE}&station=SRI-Lanka")
    assert r.status_code == 200
    body = r.json()
    assert body["station"] == "SRI-Lanka"
    assert body["image_url"].endswith("SRI-Lanka_20260615_051500_v3.png")
    # Latest segment (05:15) should have been the one rendered.
    assert render.call_args.args[0].filename == "SRI-Lanka_20260615_051500_59.fit.gz"


async def test_archive_spectrum_404_when_station_absent(client):
    with patch.object(svc, "list_day_files", new=AsyncMock(return_value=_DAY_FILES)):
        r = await client.get(f"/api/radio/archive/spectrum?date={_DATE}&station=NOPE")
    assert r.status_code == 404


async def test_bursts_by_date_filters_and_resolves(client):
    with patch.object(svc, "fetch_burst_list_text", new=AsyncMock(return_value=_BURST_TEXT)), patch.object(
        svc, "list_day_files", new=AsyncMock(return_value=_DAY_FILES)
    ):
        r = await client.get(f"/api/radio/bursts?date={_DATE}")
    assert r.status_code == 200
    body = r.json()
    assert body["date"] == _DATE
    assert body["count"] == 2  # the 06-14 event is excluded
    first = body["events"][0]
    assert first["burst_type"] == "III"
    assert first["station_used"] == "SRI-Lanka"
    assert first["has_fits"] is True


async def test_burst_spectrum_by_date(client):
    with patch.object(svc, "fetch_burst_list_text", new=AsyncMock(return_value=_BURST_TEXT)), patch.object(
        svc, "list_day_files", new=AsyncMock(return_value=_DAY_FILES)
    ), patch.object(svc, "_render_archive_file", new=AsyncMock(return_value=_META)):
        r = await client.get(f"/api/radio/bursts/spectrum?date={_DATE}&index=0")
    assert r.status_code == 200
    body = r.json()
    assert body["index"] == 0
    assert body["station_used"] == "SRI-Lanka"
    assert body["image_url"].endswith(".png")


async def test_bad_date_returns_400(client):
    r = await client.get("/api/radio/archive/stations?date=15-06-2026")
    assert r.status_code == 400


async def test_archive_spectrum_exposes_fits_filename(client):
    with patch.object(svc, "list_day_files", new=AsyncMock(return_value=_DAY_FILES)), patch.object(
        svc, "_render_archive_file", new=AsyncMock(return_value=_META)
    ):
        r = await client.get(f"/api/radio/archive/spectrum?date={_DATE}&station=SRI-Lanka")
    assert r.status_code == 200
    assert r.json()["fits_filename"] == "SRI-Lanka_20260615_051500_59.fit.gz"


async def test_archive_fits_download(client):
    fname = "SRI-Lanka_20260615_051500_59.fit.gz"
    with patch.object(svc, "list_day_files", new=AsyncMock(return_value=_DAY_FILES)), patch.object(
        svc, "fetch_fits_bytes", new=AsyncMock(return_value=b"\x1f\x8bRAWFITS")
    ):
        r = await client.get(
            f"/api/radio/archive/fits?date={_DATE}&station=SRI-Lanka&filename={fname}"
        )
    assert r.status_code == 200
    assert r.content == b"\x1f\x8bRAWFITS"
    assert r.headers["content-type"] == "application/gzip"
    assert f'attachment; filename="{fname}"' in r.headers["content-disposition"]


async def test_archive_fits_404_when_missing(client):
    with patch.object(svc, "list_day_files", new=AsyncMock(return_value=_DAY_FILES)):
        r = await client.get(
            f"/api/radio/archive/fits?date={_DATE}&station=SRI-Lanka&filename=nope.fit.gz"
        )
    assert r.status_code == 404


async def test_png_download_sets_attachment(client, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "data_dir", str(tmp_path))
    settings.ensure_dirs()
    name = "demo_v3.png"
    (tmp_path / "spectra" / name).write_bytes(b"\x89PNG\r\n\x1a\n")

    inline = await client.get(f"/api/radio/spectra/{name}")
    assert inline.status_code == 200
    assert "attachment" not in inline.headers.get("content-disposition", "")

    dl = await client.get(f"/api/radio/spectra/{name}?download=1")
    assert dl.status_code == 200
    assert "attachment" in dl.headers["content-disposition"]


async def test_png_path_traversal_blocked(client):
    r = await client.get("/api/radio/spectra/..%2f..%2fconfig.py")
    assert r.status_code == 404
