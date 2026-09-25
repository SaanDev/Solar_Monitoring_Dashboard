"""Tests for the SDO/AIA Data Analysis feature (offline).

Uses SunPy's bundled sample AIA frame so no live VSO/JSOC/HEK access is needed.
Covers the session/upload + plot/crop/difference render paths, the options and
error responses, and the background job-manager lifecycle.
"""
import time
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from app.config import settings
from app.main import app
from app.services.job_manager import JobManager


@pytest.fixture(scope="module")
def aia_bytes() -> bytes:
    import sunpy.data.sample as sample  # downloads once, then cached locally

    return Path(sample.AIA_171_IMAGE).read_bytes()


@pytest.fixture(autouse=True)
def isolated_data_dir(tmp_path, monkeypatch):
    """Point session storage at a temp dir so tests don't pollute DATA_DIR."""
    monkeypatch.setattr(settings, "data_dir", str(tmp_path))


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


def _upload(content: bytes, n: int = 1):
    return [("files", (f"AIA_171_{i}.fits", content, "application/fits")) for i in range(n)]


async def test_options(client):
    r = await client.get("/api/analysis/options")
    assert r.status_code == 200
    body = r.json()
    assert any(w["code"] == "171" for w in body["wavelengths"])
    assert "auto" in body["colormaps"]
    assert "RdBu_r" in body["colormaps"]
    assert body["difference_types"] == ["running", "base"]
    assert "mp4" in body["movie_formats"]


async def test_upload_and_render_plot(client, aia_bytes):
    r = await client.post("/api/analysis/source/upload", files=_upload(aia_bytes))
    assert r.status_code == 200, r.text
    session = r.json()
    assert session["instrument"].startswith("AIA")
    assert session["wavelength_angstrom"] == pytest.approx(171.0, abs=1.0)
    assert session["n_frames"] == 1

    # Default plot
    r = await client.get("/api/analysis/render", params={"session": session["id"]})
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/png"
    assert len(r.content) > 5000

    # Crop + named cmap + sqrt scale + download headers
    r = await client.get("/api/analysis/render", params={
        "session": session["id"], "cmap": "sdoaia171", "scale": "sqrt",
        "crop": "true", "bl_x": -900, "bl_y": -900, "tr_x": 900, "tr_y": 900,
        "draw_limb": "true", "download": "true",
    })
    assert r.status_code == 200
    assert "attachment" in r.headers.get("content-disposition", "")
    assert len(r.content) > 5000


async def test_render_errors(client, aia_bytes):
    r = await client.post("/api/analysis/source/upload", files=_upload(aia_bytes))
    sid = r.json()["id"]

    # Invalid colormap → 422
    r = await client.get("/api/analysis/render", params={"session": sid, "cmap": "nope"})
    assert r.status_code == 422

    # Unknown session → 404
    r = await client.get("/api/analysis/render", params={"session": "0" * 32})
    assert r.status_code == 404

    # Malformed id → 400/404 (never a 500)
    r = await client.get("/api/analysis/render", params={"session": "bad-id"})
    assert r.status_code in (400, 404, 422)


async def test_upload_rejects_non_fits(client):
    r = await client.post(
        "/api/analysis/source/upload",
        files=[("files", ("notes.txt", b"hello", "text/plain"))],
    )
    assert r.status_code == 400


async def test_difference(client, aia_bytes):
    # Two frames (same sample twice) make a valid 2-frame sequence.
    r = await client.post("/api/analysis/source/upload", files=_upload(aia_bytes, n=2))
    session = r.json()
    assert session["n_frames"] == 2
    sid = session["id"]

    r = await client.get("/api/analysis/difference", params={
        "session": sid, "frame": 1, "diff_type": "running",
    })
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/png"
    assert len(r.content) > 5000

    # Running difference on frame 0 has no predecessor → 422
    r = await client.get("/api/analysis/difference", params={
        "session": sid, "frame": 0, "diff_type": "running",
    })
    assert r.status_code == 422


async def test_active_regions_threshold(client, aia_bytes):
    """Threshold detection is local (scipy) — no HEK network needed."""
    r = await client.post("/api/analysis/source/upload", files=_upload(aia_bytes))
    sid = r.json()["id"]
    r = await client.get("/api/analysis/active-regions", params={
        "session": sid, "method": "threshold", "threshold_pct": 97, "scale": "sqrt",
    })
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/png"
    assert len(r.content) > 5000


async def test_job_not_found(client):
    r = await client.get("/api/analysis/jobs/deadbeef")
    assert r.status_code == 404


# ── job manager (no app, no network) ───────────────────────────────────────────


def _await_job(jm: JobManager, jid: str, timeout: float = 5.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        job = jm.get(jid)
        if job and job.state in ("done", "error"):
            return job
        time.sleep(0.02)
    raise AssertionError("job did not settle in time")


def test_job_manager_success():
    jm = JobManager()
    seen = {}

    def work(progress):
        progress(0.5, "halfway")
        seen["msg"] = "ran"
        return ("/tmp/out.mp4", {"kind": "artifact", "format": "mp4"})

    jid = jm.submit(work)
    job = _await_job(jm, jid)
    assert job.state == "done"
    assert job.progress == 1.0
    assert job.result_path == "/tmp/out.mp4"
    assert job.result_meta == {"kind": "artifact", "format": "mp4"}
    assert seen["msg"] == "ran"


def test_job_manager_error():
    jm = JobManager()

    def boom(progress):
        raise RuntimeError("kaboom")

    jid = jm.submit(boom)
    job = _await_job(jm, jid)
    assert job.state == "error"
    assert "kaboom" in (job.error or "")
