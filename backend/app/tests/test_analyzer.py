"""Tests for the e-CALLISTO Analyzer: processing functions + API endpoints.

Filesystem is isolated to a tmp dir per test (settings.data_dir is monkeypatched),
and a synthetic in-memory e-CALLISTO FITS stands in for a real upload.
"""
import io
from unittest.mock import AsyncMock

import numpy as np
import pytest
from astropy.io import fits
from httpx import ASGITransport, AsyncClient

from app.config import settings
from app.main import app
from app.processing.analyzer_processing import (
    COLORMAPS,
    convert_digits_to_db,
    default_limits,
    process_spectrum,
    resolve_cmap,
    subtract_background_rows,
)


def _fits_bytes(n_freq: int = 120, n_time: int = 1200) -> bytes:
    rng = np.random.default_rng(7)
    data = rng.uniform(60, 100, size=(n_freq, n_time)).astype(np.float32)
    data[40:60, 400:460] += 180  # a burst-like feature
    prim = fits.PrimaryHDU(data)
    prim.header["DATE-OBS"] = "2024/01/15"
    prim.header["TIME-OBS"] = "10:00:00.000"
    prim.header["FRQMIN"] = 45.0
    prim.header["FRQMAX"] = 870.0
    tcol = fits.Column(name="TIME", format=f"{n_time}E",
                       array=np.linspace(0, 900, n_time).reshape(1, n_time))
    fcol = fits.Column(name="FREQUENCY", format=f"{n_freq}E",
                       array=np.linspace(870, 45, n_freq).reshape(1, n_freq))
    buf = io.BytesIO()
    fits.HDUList([prim, fits.BinTableHDU.from_columns([tcol, fcol])]).writeto(buf)
    return buf.getvalue()


@pytest.fixture(autouse=True)
def isolate_data_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "data_dir", str(tmp_path))


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


async def _upload(client) -> dict:
    r = await client.post(
        "/api/analyzer/upload",
        files={"file": ("synthetic.fits", _fits_bytes(), "application/octet-stream")},
        data={"station": "TEST-STN"},
    )
    assert r.status_code == 200, r.text
    return r.json()


# ── Processing ───────────────────────────────────────────────────────────────


def test_subtract_background_rows_methods():
    # Row 0 baseline ~10 (constant), row 1 has an outlier so mean != median.
    data = np.array([[10, 10, 10, 10], [0, 0, 0, 100]], dtype=np.float32)
    mean = subtract_background_rows(data, "mean")
    assert np.allclose(mean[0], 0.0)
    median = subtract_background_rows(data, "median")
    assert np.allclose(median[1, :3], 0.0)        # median baseline = 0
    robust = subtract_background_rows(data, "robust")
    assert robust.shape == data.shape


def test_subtract_background_rows_rejects_bad_method():
    with pytest.raises(ValueError):
        subtract_background_rows(np.zeros((2, 2), np.float32), "bogus")


def test_convert_digits_to_db_is_linear():
    arr = np.array([[0.0, 255.0]], dtype=np.float32)
    out = convert_digits_to_db(arr, cold_digits=0.0)
    assert out[0, 0] == 0.0
    assert out[0, 1] > 0.0


def test_default_limits_by_unit():
    data = np.linspace(0, 100, 1000).reshape(10, 100).astype(np.float32)
    assert default_limits(data, "db") == (-1.0, 8.0)
    lo, hi = default_limits(data, "digits")
    assert lo < hi


def test_resolve_cmap_allowlist():
    assert resolve_cmap("custom") is not None
    assert resolve_cmap("viridis") is not None
    with pytest.raises(ValueError):
        resolve_cmap("not-a-cmap")


def test_process_spectrum_labels_and_rfi():
    data = np.random.default_rng(0).uniform(60, 100, size=(20, 50)).astype(np.float32)
    arr_db, label_db = process_spectrum(data, intensity_unit="db", method="median")
    assert label_db == "dB above background" and arr_db.shape == data.shape
    arr_dig, label_dig = process_spectrum(
        data, intensity_unit="digits", method="mean", rfi_enabled=True, rfi_low=1, rfi_high=99
    )
    assert label_dig == "counts above background"


# ── API ──────────────────────────────────────────────────────────────────────


async def test_upload_returns_session(client):
    s = await _upload(client)
    assert s["n_freq"] == 120 and s["n_time"] == 1200
    assert s["station"] == "TEST-STN"
    assert abs(s["freq_min_mhz"] - 45.0) < 1 and abs(s["freq_max_mhz"] - 870.0) < 1
    assert len(s["id"]) == 32


async def test_upload_rejects_non_fits(client):
    r = await client.post(
        "/api/analyzer/upload",
        files={"file": ("notes.txt", b"hello", "text/plain")},
    )
    assert r.status_code == 400


async def test_colormaps_endpoint(client):
    r = await client.get("/api/analyzer/colormaps")
    assert r.status_code == 200
    body = r.json()
    assert "magma" in body["colormaps"] and "median" in body["methods"]
    assert set(COLORMAPS) == set(body["colormaps"])


async def test_stats_defaults(client):
    s = await _upload(client)
    r = await client.get("/api/analyzer/stats", params={"id": s["id"], "intensity_unit": "db"})
    assert r.status_code == 200
    body = r.json()
    assert body["vmin"] == -1.0 and body["vmax"] == 8.0
    assert body["data_min"] < body["data_max"]


@pytest.mark.parametrize("unit,cmap", [("db", "viridis"), ("digits", "custom")])
async def test_render_returns_png(client, unit, cmap):
    s = await _upload(client)
    r = await client.get(
        "/api/analyzer/render",
        params={"id": s["id"], "intensity_unit": unit, "cmap": cmap, "time_unit": "utc"},
    )
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/png"
    assert len(r.content) > 1000


async def test_render_bad_cmap_422(client):
    s = await _upload(client)
    r = await client.get("/api/analyzer/render", params={"id": s["id"], "cmap": "nope"})
    assert r.status_code == 422


async def test_render_unknown_id_404(client):
    r = await client.get("/api/analyzer/render", params={"id": "0" * 32})
    assert r.status_code == 404


async def test_render_malformed_id_422(client):
    r = await client.get("/api/analyzer/render", params={"id": "../etc"})
    assert r.status_code == 422


async def test_export_fits_is_valid(client):
    s = await _upload(client)
    r = await client.get(
        "/api/analyzer/export", params={"id": s["id"], "format": "fits", "intensity_unit": "db"}
    )
    assert r.status_code == 200
    assert "attachment" in r.headers["content-disposition"]
    hdul = fits.open(io.BytesIO(r.content))
    assert hdul[0].data.shape == (120, 1200)
    assert hdul[0].header["BGSUB"] == "median"


async def test_export_png_attachment(client):
    s = await _upload(client)
    r = await client.get("/api/analyzer/export", params={"id": s["id"], "format": "png"})
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/png"
    assert "attachment" in r.headers["content-disposition"]


async def test_from_archive_uses_existing_archive(client, monkeypatch):
    monkeypatch.setattr(
        "app.services.analyzer_service.get_archive_fits",
        AsyncMock(return_value=(_fits_bytes(), "ALASKA_20240115_100000_59.fit.gz")),
    )
    r = await client.post(
        "/api/analyzer/from-archive",
        params={"date": "2024-01-15", "station": "ALASKA-COHOE", "filename": "x.fit.gz"},
    )
    assert r.status_code == 200
    assert r.json()["n_time"] == 1200


# ── Combine (time / frequency) ────────────────────────────────────────────────


def _band_fits(n_freq: int, n_time: int, fmin: float, fmax: float, time_obs="10:00:00.000") -> bytes:
    rng = np.random.default_rng(int(fmin) + n_freq)
    data = rng.uniform(60, 100, size=(n_freq, n_time)).astype(np.float32)
    prim = fits.PrimaryHDU(data)
    prim.header["DATE-OBS"] = "2024/01/15"
    prim.header["TIME-OBS"] = time_obs
    prim.header["FRQMIN"] = fmin
    prim.header["FRQMAX"] = fmax
    t = fits.Column(name="TIME", format=f"{n_time}E",
                    array=np.linspace(0, 900, n_time).reshape(1, n_time))
    f = fits.Column(name="FREQUENCY", format=f"{n_freq}E",
                    array=np.linspace(fmax, fmin, n_freq).reshape(1, n_freq))
    buf = io.BytesIO()
    fits.HDUList([prim, fits.BinTableHDU.from_columns([t, f])]).writeto(buf)
    return buf.getvalue()


async def _upload_band(client, **kw) -> dict:
    r = await client.post(
        "/api/analyzer/upload",
        files={"file": ("band.fits", _band_fits(**kw), "application/octet-stream")},
        data={"station": "S"},
    )
    assert r.status_code == 200, r.text
    return r.json()


async def test_combine_frequency_merges_bands(client):
    a = await _upload_band(client, n_freq=100, n_time=600, fmin=45, fmax=200)
    b = await _upload_band(client, n_freq=80, n_time=600, fmin=200, fmax=400)
    r = await client.post(f"/api/analyzer/combine?ids={a['id']}&ids={b['id']}&mode=frequency")
    assert r.status_code == 200, r.text
    s = r.json()
    assert s["n_time"] == 600
    assert s["freq_min_mhz"] <= 46 and s["freq_max_mhz"] >= 399
    # The combined session renders like any other.
    rr = await client.get("/api/analyzer/render", params={"id": s["id"], "cmap": "viridis"})
    assert rr.status_code == 200 and rr.headers["content-type"] == "image/png"


async def test_combine_time_extends_axis(client):
    a = await _upload_band(client, n_freq=100, n_time=600, fmin=45, fmax=200, time_obs="10:00:00.000")
    b = await _upload_band(client, n_freq=100, n_time=600, fmin=45, fmax=200, time_obs="10:15:00.000")
    r = await client.post(f"/api/analyzer/combine?ids={a['id']}&ids={b['id']}&mode=time")
    assert r.status_code == 200, r.text
    s = r.json()
    assert s["n_time"] == 1200
    assert s["duration_s"] > 1000  # ~two 15-min segments


async def test_combine_needs_two_files(client):
    a = await _upload_band(client, n_freq=50, n_time=100, fmin=45, fmax=200)
    r = await client.post(f"/api/analyzer/combine?ids={a['id']}&mode=time")
    assert r.status_code == 422


async def test_combine_time_rejects_mismatched_freq(client):
    a = await _upload_band(client, n_freq=100, n_time=600, fmin=45, fmax=200)
    b = await _upload_band(client, n_freq=80, n_time=600, fmin=200, fmax=400)
    r = await client.post(f"/api/analyzer/combine?ids={a['id']}&ids={b['id']}&mode=time")
    assert r.status_code == 422


# ── Project (.efaproj) save / open ────────────────────────────────────────────


async def test_project_round_trip(client):
    s = await _upload(client)
    params = {
        "id": s["id"], "intensity_unit": "db", "time_unit": "utc",
        "cmap": "viridis", "vmin": -1.0, "vmax": 8.0,
    }
    r = await client.get("/api/analyzer/project", params=params)
    assert r.status_code == 200
    assert "attachment" in r.headers["content-disposition"]
    assert r.headers["content-disposition"].endswith('.efaproj"')

    # The download is a valid .efaproj zip (meta.json magic + arrays.npz).
    import zipfile
    zf = zipfile.ZipFile(io.BytesIO(r.content))
    assert set(zf.namelist()) == {"meta.json", "arrays.npz"}
    import json
    meta = json.loads(zf.read("meta.json"))
    assert meta["magic"] == "e-callisto-fits-analyzer-project"
    assert meta["schema_version"] == 1
    assert meta["use_db"] is True and meta["use_utc"] is True

    # Re-open it -> a new session with the saved settings.
    rr = await client.post(
        "/api/analyzer/open-project",
        files={"file": ("p.efaproj", r.content, "application/octet-stream")},
    )
    assert rr.status_code == 200, rr.text
    body = rr.json()
    assert body["session"]["n_freq"] == 120 and body["session"]["n_time"] == 1200
    assert body["settings"]["intensity_unit"] == "db"
    assert body["settings"]["time_unit"] == "utc"
    assert body["settings"]["cmap"] == "viridis"


async def test_open_desktop_style_project(client):
    """A project written like the desktop app (raw arrays + desktop meta, proper
    FITS header card images) opens in the web tool with start time + settings."""
    from app.processing.efaproj import write_project

    hdr = fits.Header()
    hdr["DATE-OBS"] = "2024/01/15"
    hdr["TIME-OBS"] = "11:30:00.000"
    hdr["FRQMIN"] = 45.0
    hdr["FRQMAX"] = 870.0
    hdr["CONTENT"] = "DESKTOP-STN"
    header_txt = hdr.tostring(sep="\n", endcard=True, padding=False)

    buf = io.BytesIO()
    write_project(
        buf,
        meta={
            "use_db": True, "use_utc": False, "cmap": "Custom",
            "noise_vmin": -1.0, "noise_vmax": 9.0,
            "filename": "DESK_20240115", "fits_header": header_txt,
        },
        arrays={
            "raw_data": np.random.default_rng(0).uniform(60, 100, (80, 600)).astype(np.float32),
            "freqs": np.linspace(870, 45, 80).astype(np.float32),
            "time": np.linspace(0, 450, 600).astype(np.float32),
        },
    )

    r = await client.post(
        "/api/analyzer/open-project",
        files={"file": ("desk.efaproj", buf.getvalue(), "application/octet-stream")},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["session"]["station"] == "DESKTOP-STN"
    assert body["session"]["start_time"] is not None  # parsed from the desktop header
    assert body["settings"]["cmap"] == "custom"        # "Custom" -> web "custom"
    assert body["settings"]["intensity_unit"] == "db"
    assert body["settings"]["vmax"] == 9.0


async def test_open_project_rejects_non_efaproj(client):
    r = await client.post(
        "/api/analyzer/open-project",
        files={"file": ("x.txt", b"nope", "text/plain")},
    )
    assert r.status_code == 400
