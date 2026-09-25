"""Startup behaviour: the automatic DB migration must run, but a migration
failure must never crash startup (the rest of the app should still serve)."""
import app.main as main


async def test_apply_migrations_runs_upgrade(monkeypatch):
    calls: list[bool] = []
    monkeypatch.setattr(main, "_alembic_upgrade_head", lambda: calls.append(True))

    await main._apply_migrations()

    assert calls == [True]


async def test_apply_migrations_never_raises(monkeypatch):
    def _boom() -> None:
        raise RuntimeError("database unreachable")

    monkeypatch.setattr(main, "_alembic_upgrade_head", _boom)

    # Must complete without raising so startup continues even if migration fails.
    await main._apply_migrations()


async def test_lifespan_runs_migration_on_startup(monkeypatch):
    from app.config import settings

    calls: list[bool] = []
    monkeypatch.setattr(main, "_alembic_upgrade_head", lambda: calls.append(True))
    monkeypatch.setattr(settings, "auto_migrate", True)
    monkeypatch.setattr(settings, "enable_scheduler", False)  # don't start the scheduler

    async with main.lifespan(main.app):
        pass

    assert calls == [True]  # startup applied migrations exactly once
