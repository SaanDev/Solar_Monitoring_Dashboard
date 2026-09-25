"""The full migration chain must run on SQLite: the desktop app auto-migrates a
fresh SQLite file on first launch (and every later launch after an update)."""
import sqlite3
from contextlib import closing
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

from app.config import settings
from app.database import Base
from app.main import _alembic_upgrade_head


def _head_revision() -> str:
    cfg = Config()
    cfg.set_main_option("script_location", str(Path(__file__).resolve().parents[2] / "alembic"))
    return ScriptDirectory.from_config(cfg).get_current_head()


def test_upgrade_head_on_fresh_sqlite_file(tmp_path, monkeypatch):
    db = tmp_path / "dashboard.db"
    monkeypatch.setattr(settings, "database_url", f"sqlite+aiosqlite:///{db.as_posix()}")

    _alembic_upgrade_head()
    _alembic_upgrade_head()  # already at head: must be a clean no-op

    with closing(sqlite3.connect(db)) as conn:
        version = conn.execute("SELECT version_num FROM alembic_version").fetchone()[0]
        tables = {
            name: {row[1] for row in conn.execute(f"PRAGMA table_info('{name}')")}
            for (name,) in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }

    assert version == _head_revision()
    # Every model table and column exists in the migrated schema — a model
    # change without a migration would break the desktop DB (and the website's).
    for name, table in Base.metadata.tables.items():
        assert name in tables, f"table {name} missing after migration"
        missing = {c.name for c in table.columns} - tables[name]
        assert not missing, f"{name}: columns {missing} missing after migration"
