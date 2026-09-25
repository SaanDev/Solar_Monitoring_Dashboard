"""Entry point for the desktop app (Windows and Linux): ``python -m app.desktop``.

The Electron shell (``desktop/``) spawns this with a bundled Python. It runs the
same FastAPI app the website uses, reconfigured to need nothing else on the
machine:

* SQLite file instead of Postgres/TimescaleDB (the repositories and migrations
  are already dialect-aware),
* an in-process cache instead of Redis (``REDIS_URL=memory://``),
* the Next.js static export served at "/" on the same origin as ``/api``.

Environment (all optional, set by the Electron launcher):

``SWD_HOME``          per-user data root (DB, data files, logs, user ``.env``).
                      Default: ``%LOCALAPPDATA%\\SolarDashboard`` on Windows,
                      ``$XDG_DATA_HOME/SolarDashboard`` (``~/.local/share/...``)
                      on Linux.
``SWD_PORT``          port on 127.0.0.1. Default 47800 — fixed so the page origin,
                      and with it the browser's localStorage, is stable.
``SWD_FRONTEND_DIR``  directory of the static export (``frontend/out``).
``SWD_LIFELINE``      ``stdin``: shut down cleanly when stdin reaches EOF or reads
                      ``quit``. The parent holds the pipe, so if it dies the
                      backend follows instead of being orphaned (on Windows a
                      killed parent can't take its children down).

Any regular setting (``JSOC_EMAIL``, ``TELEGRAM_BOT_TOKEN``, ...) can go in
``SWD_HOME/.env``; the working directory is moved there so pydantic-settings
finds it. The variables set below are defaults only — the real environment wins.
"""
from __future__ import annotations

import logging
import logging.handlers
import os
import sys
import threading
from pathlib import Path

DEFAULT_PORT = 47800


def _default_home() -> Path:
    """Same folder as HOME in desktop/src/paths.ts."""
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA")
        return Path(base) / "SolarDashboard" if base else Path.home() / ".solar-dashboard"
    # The XDG data dir; the spec says to ignore an empty or relative value.
    xdg = os.environ.get("XDG_DATA_HOME", "")
    base = Path(xdg) if os.path.isabs(xdg) else Path.home() / ".local" / "share"
    return base / "SolarDashboard"


def _configure_environment(home: Path, port: int) -> None:
    """Point every setting at the desktop runtime. Must run before ``app.config``
    is imported, because ``Settings()`` is instantiated at import time."""
    origins = f"http://127.0.0.1:{port},http://localhost:{port}"
    defaults = {
        "DATABASE_URL": f"sqlite+aiosqlite:///{(home / 'dashboard.db').as_posix()}",
        "REDIS_URL": "memory://",
        "DATA_DIR": str(home / "data"),
        "DESKTOP_MODE": "true",
        "CORS_ORIGINS": origins,
    }
    frontend = os.environ.get("SWD_FRONTEND_DIR")
    if frontend:
        defaults["FRONTEND_DIST_DIR"] = str(Path(frontend).resolve())
    for key, value in defaults.items():
        os.environ.setdefault(key, value)


class _DropClientResets(logging.Filter):
    """Windows' proactor event loop logs a full traceback (WinError 10054)
    whenever the browser drops a connection mid-request — every quick page
    change. Harmless, but it buries real errors in the log."""

    def filter(self, record: logging.LogRecord) -> bool:
        exc = record.exc_info[1] if record.exc_info else None
        return not isinstance(exc, ConnectionResetError)


def _configure_logging(home: Path, level: str, quiet_console: bool) -> None:
    log_dir = home / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    file_handler = logging.handlers.RotatingFileHandler(
        log_dir / "backend.log", maxBytes=5_000_000, backupCount=3, encoding="utf-8"
    )
    file_handler.setFormatter(fmt)
    console = logging.StreamHandler(sys.stderr)
    console.setFormatter(fmt)
    # Under Electron, stderr goes to a per-launch file that only has to explain
    # a failed start; the rotating backend.log above has everything else.
    if quiet_console:
        console.setLevel(logging.WARNING)
    root = logging.getLogger()
    root.handlers[:] = [file_handler, console]
    root.setLevel(level.upper())
    logging.getLogger("asyncio").addFilter(_DropClientResets())


def _watch_stdin(server) -> None:
    """Ask uvicorn to exit when the parent closes our stdin or says ``quit``."""

    def _run() -> None:
        try:
            for line in sys.stdin:
                if line.strip().lower() == "quit":
                    break
        except (OSError, ValueError):
            pass
        logging.getLogger(__name__).info("lifeline closed; shutting down")
        server.should_exit = True

    threading.Thread(target=_run, name="stdin-lifeline", daemon=True).start()


def main() -> None:
    home = Path(os.environ.get("SWD_HOME") or _default_home()).resolve()
    port = int(os.environ.get("SWD_PORT") or DEFAULT_PORT)
    home.mkdir(parents=True, exist_ok=True)
    os.chdir(home)
    _configure_environment(home, port)

    # Imported only now: both read the environment prepared above.
    import uvicorn

    from app.config import settings
    from app.main import app

    lifeline = os.environ.get("SWD_LIFELINE", "").lower() == "stdin"
    _configure_logging(home, settings.log_level, quiet_console=lifeline)
    logging.getLogger(__name__).info(
        "desktop backend starting on 127.0.0.1:%d (home=%s)", port, home
    )

    server = uvicorn.Server(
        uvicorn.Config(
            app,
            host="127.0.0.1",
            port=port,
            log_config=None,  # keep the handlers configured above
            log_level=settings.log_level,
            # The UI polls ~20 endpoints every minute or so; a line per request
            # would rotate the useful history out of backend.log within days.
            access_log=False,
        )
    )
    if lifeline:
        _watch_stdin(server)
    server.run()


if __name__ == "__main__":
    main()
