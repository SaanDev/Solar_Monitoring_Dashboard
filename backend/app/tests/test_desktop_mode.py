"""Desktop-app runtime pieces: in-process cache, UTC-aware datetimes on SQLite,
the static frontend mount, the cross-origin write guard (app/main.py) and the
per-user data folder (app/desktop.py)."""
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select

import app.cache as cache_module
import app.desktop as desktop
from app.cache import MemoryCache, get_client as real_get_client
from app.config import settings
from app.main import _DesktopOriginGuard, _FrontendFiles
from app.models import GoesXrs


# ── in-process cache ──────────────────────────────────────────────────────────

async def test_memory_cache_expires_entries(monkeypatch):
    now = [1000.0]
    monkeypatch.setattr(cache_module.time, "monotonic", lambda: now[0])
    cache = MemoryCache()

    await cache.set("k", "v", ex=60)
    await cache.set("forever", "x")
    assert await cache.get("k") == "v"

    now[0] += 61
    assert await cache.get("k") is None
    assert await cache.get("forever") == "x"
    assert await cache.get("missing") is None


async def test_memory_cache_sweeps_unread_expired_keys(monkeypatch):
    now = [0.0]
    monkeypatch.setattr(cache_module.time, "monotonic", lambda: now[0])
    cache = MemoryCache()
    await cache.set("stale", "v", ex=1)
    now[0] += 10
    for i in range(MemoryCache._SWEEP_EVERY):
        await cache.set(f"k{i}", "v", ex=100)
    assert "stale" not in cache._store


@pytest.mark.parametrize("url", ["memory://", "", "  "])
def test_get_client_uses_memory_cache_without_redis(monkeypatch, url):
    monkeypatch.setattr(settings, "redis_url", url)
    monkeypatch.setattr(cache_module, "_client", None)
    assert isinstance(real_get_client(), MemoryCache)


def test_get_client_keeps_redis_for_redis_urls(monkeypatch):
    monkeypatch.setattr(settings, "redis_url", "redis://localhost:6379/0")
    monkeypatch.setattr(cache_module, "_client", None)
    assert not isinstance(real_get_client(), MemoryCache)


# ── UTC-aware datetimes on SQLite ─────────────────────────────────────────────

async def test_sqlite_datetimes_come_back_utc_aware(db_session):
    # 12:00 at UTC+05:30 is 06:30 UTC; SQLite has no tz type, so without
    # UTCDateTime this would read back as a naive 12:00.
    local = datetime(2026, 9, 1, 12, 0, tzinfo=timezone(timedelta(hours=5, minutes=30)))
    db_session.add(GoesXrs(time=local, source="test", short_channel=1e-6, long_channel=1e-5))
    await db_session.commit()
    db_session.expunge_all()

    row = (await db_session.execute(select(GoesXrs))).scalar_one()
    assert row.time.tzinfo is not None
    assert row.time == datetime(2026, 9, 1, 6, 30, tzinfo=timezone.utc)
    assert row.ingested_at.tzinfo is not None

    # Aware bound parameters compare in UTC too.
    hit = await db_session.execute(
        select(GoesXrs).where(GoesXrs.time >= datetime(2026, 9, 1, 6, 30, tzinfo=timezone.utc))
    )
    assert hit.scalar_one_or_none() is not None
    miss = await db_session.execute(
        select(GoesXrs).where(GoesXrs.time > datetime(2026, 9, 1, 6, 30, tzinfo=timezone.utc))
    )
    assert miss.scalar_one_or_none() is None


# ── static frontend mount ─────────────────────────────────────────────────────

@pytest.fixture
def frontend_app(tmp_path):
    (tmp_path / "index.html").write_text("<p>overview</p>")
    (tmp_path / "archive").mkdir()
    (tmp_path / "archive" / "index.html").write_text("<p>archive</p>")
    (tmp_path / "404.html").write_text("<p>not found</p>")

    app = FastAPI()

    @app.get("/api/status")
    def status():
        return {"status": "ok"}

    app.mount("/", _FrontendFiles(directory=tmp_path, html=True), name="frontend")
    return TestClient(app)


def test_frontend_mount_serves_pages(frontend_app):
    assert "overview" in frontend_app.get("/").text
    assert "archive" in frontend_app.get("/archive/").text
    # trailingSlash export: the bare path redirects to the directory index.
    r = frontend_app.get("/archive", follow_redirects=False)
    assert r.status_code in (307, 308) and r.headers["location"].endswith("/archive/")


def test_frontend_mount_does_not_shadow_api(frontend_app):
    assert frontend_app.get("/api/status").json() == {"status": "ok"}
    r = frontend_app.get("/api/does-not-exist")
    assert r.status_code == 404
    assert r.json() == {"detail": "Not Found"}


def test_frontend_mount_unknown_page_gets_404_page(frontend_app):
    r = frontend_app.get("/no-such-page/")
    assert r.status_code == 404
    assert "not found" in r.text


# ── cross-origin write guard ──────────────────────────────────────────────────

@pytest.fixture
def guarded_app():
    app = FastAPI()

    @app.post("/api/thing")
    def post_thing():
        return {"ok": True}

    @app.get("/api/thing")
    def get_thing():
        return {"ok": True}

    app.add_middleware(_DesktopOriginGuard, allowed_origins=["http://127.0.0.1:47800"])
    return TestClient(app)


def test_origin_guard_blocks_foreign_writes(guarded_app):
    r = guarded_app.post("/api/thing", headers={"Origin": "https://evil.example"})
    assert r.status_code == 403
    assert guarded_app.post("/api/thing", headers={"Origin": "null"}).status_code == 403


def test_origin_guard_allows_app_origin_and_local_clients(guarded_app):
    assert guarded_app.post("/api/thing", headers={"Origin": "http://127.0.0.1:47800"}).status_code == 200
    assert guarded_app.post("/api/thing").status_code == 200  # no Origin: curl / scripts


def test_origin_guard_ignores_reads(guarded_app):
    assert guarded_app.get("/api/thing", headers={"Origin": "https://evil.example"}).status_code == 200


# ── per-user data folder (must match HOME in desktop/src/paths.ts) ────────────

def _platform(monkeypatch, name):
    monkeypatch.setattr(desktop, "sys", SimpleNamespace(platform=name))


def test_default_home_on_windows_is_localappdata(monkeypatch, tmp_path):
    _platform(monkeypatch, "win32")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    assert desktop._default_home() == tmp_path / "SolarDashboard"


def test_default_home_on_linux_follows_xdg_data_home(monkeypatch, tmp_path):
    _platform(monkeypatch, "linux")
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    assert desktop._default_home() == tmp_path / "SolarDashboard"


@pytest.mark.parametrize("xdg", [None, "", "relative/share"])
def test_default_home_on_linux_falls_back_to_local_share(monkeypatch, tmp_path, xdg):
    _platform(monkeypatch, "linux")
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    if xdg is None:
        monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    else:
        monkeypatch.setenv("XDG_DATA_HOME", xdg)
    assert desktop._default_home() == tmp_path / ".local" / "share" / "SolarDashboard"
