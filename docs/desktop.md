# Desktop app (Windows)

The dashboard ships as an installable Windows app alongside the website. It is
the same backend and the same UI, packaged so that a single installer is all a
machine needs: no Docker, Postgres, Redis, Python or Node.

## How it works

```
Solar Monitoring Dashboard.exe   Electron: window, tray, toasts, auto-update  (desktop/src)
  └─ resources\python\python.exe -P -m app.desktop        stdin pipe = lifeline
       FastAPI + APScheduler + in-process ML   on 127.0.0.1:47800
       ├─ /api/*   the website's API, unchanged
       ├─ /        the Next.js static export (resources\frontend)
       ├─ DB       SQLite (WAL)   %LOCALAPPDATA%\SolarDashboard\dashboard.db
       ├─ cache    in-process TTL dict instead of Redis
       └─ files    %LOCALAPPDATA%\SolarDashboard\data
```

- **Backend** — [`backend/app/desktop.py`](../backend/app/desktop.py) points the
  normal settings at SQLite, the in-process cache and the static UI, then runs
  uvicorn. The repositories and migrations were already dialect-aware (the test
  suite runs on SQLite), so no feature is desktop-specific. Migrations run
  automatically on every start, exactly as on the server.
- **UI** — `npm run build:desktop` builds the frontend as a static export
  (`NEXT_OUTPUT=export`, same-origin API URLs via `NEXT_PUBLIC_DESKTOP=1`), and
  the backend serves it at `/`. The browser never talks cross-origin, so there is
  no CORS setup.
- **Shell** — [`desktop/`](../desktop) is a small Electron app. It starts the
  backend, shows a splash until `/api/status` answers, and then opens the window.
  It restarts the backend if it crashes, and on quit asks it to shut down cleanly
  by writing `quit` on its stdin. If the shell itself dies, the pipe closes and
  the backend exits too.
- **Python** — a relocatable CPython 3.13 build from
  [python-build-standalone](https://github.com/astral-sh/python-build-standalone),
  with the dependencies pip-installed from
  [`desktop/requirements.lock.txt`](../desktop/requirements.lock.txt). It
  includes CPU-only PyTorch, so every feature works, including burst detection.
  There's no PyInstaller freezing, so the bundle behaves like a normal install.

Closing the window hides it to the **system tray**. Ingestion, the radio-burst
scan, the offline catch-up and alert delivery keep running, and new
warning/critical alerts appear as Windows notifications. Quit from the tray menu.

## Where things live

| What | Where |
|---|---|
| App (per-user install, no admin) | `%LOCALAPPDATA%\Programs\Solar Monitoring Dashboard` |
| Database | `%LOCALAPPDATA%\SolarDashboard\dashboard.db` |
| Downloaded data, analysis sessions | `%LOCALAPPDATA%\SolarDashboard\data` |
| Logs (`backend.log`, `main.log`, `backend-console.log`) | `%LOCALAPPDATA%\SolarDashboard\logs` |
| User settings (`.env`) | `%LOCALAPPDATA%\SolarDashboard\.env` (tray → *Edit settings*) |
| Window state, browser storage | `%LOCALAPPDATA%\SolarDashboard\electron` |

The `.env` accepts any setting from [`.env.example`](../.env.example), for example
`JSOC_EMAIL` or `TELEGRAM_BOT_TOKEN`. After editing it, use tray → *Restart
backend*. The database, data folder, port and CORS are managed by the app.

**Reset:** quit the app and delete `%LOCALAPPDATA%\SolarDashboard`. Uninstalling
asks whether to delete it too; updates never touch it.

## Building an installer locally

Prerequisites: Windows 10/11 x64, Node 20+, Git LFS with the checkpoints pulled
(`git lfs pull`). No Python is needed; the build downloads its own.

```powershell
.\desktop\scripts\build.ps1
```

The first run downloads the Python runtime, PyTorch (CPU) and the scientific
stack, and caches them in `desktop/build/cache`. It then smoke-tests the runtime
(imports, all three ML checkpoints, a real start/stop of the backend). The
installer lands in `desktop/dist/`. `-SkipRuntime` reuses the staged runtime when
only the UI or shell changed.

Don't run it while `next dev` is serving from `frontend/`: like `next build`, it
rewrites `frontend/.next`. The Docker frontend is unaffected, because it keeps
`.next` in its own volume.

### Running the shell from source

```powershell
npm --prefix frontend run build:desktop   # static UI -> frontend/out
cd desktop
npm install
npm start                                 # uses backend/.venv and frontend/out
```

In dev, the shell uses `backend/.venv/Scripts/python.exe`. That venv needs the
`desktop` extra (`pip install -e ".[desktop]"`, for `aiosqlite`). Override the
locations with `SWD_PYTHON`, `SWD_BACKEND_DIR` and `SWD_FRONTEND_DIR`.

The backend alone runs without Electron too:

```powershell
$env:SWD_FRONTEND_DIR = "$PWD\frontend\out"
backend\.venv\Scripts\python.exe -m app.desktop     # http://127.0.0.1:47800
```

## Releasing

1. Bump `version` in [`desktop/package.json`](../desktop/package.json) and commit.
2. Tag and push:
   ```bash
   git tag v1.0.0-beta
   git push origin v1.0.0-beta
   ```
3. [`.github/workflows/desktop-release.yml`](../.github/workflows/desktop-release.yml)
   builds the runtime and runs the backend test suite on it. It then builds the
   installer and uploads it, with `latest.yml`, to a **draft** release
   `v1.0.0-beta`. Betas use `latest.yml` too: a beta install first asks for
   `beta.yml`, then falls back to it. The job fails if the tag and
   `package.json` disagree.
4. Review the draft on GitHub and **publish** it. Installed apps check for updates
   at startup and every 6 hours, download the update in the background, and offer
   to restart.

How installed apps find updates:

- **A prerelease install** (such as `1.0.0-beta`) scans every published release,
  newest first, and takes the first one with a semver tag. This covers later
  betas and the final `1.0.0`.
- **A stable install** only follows the release GitHub marks as **Latest**. Mark
  betas as *pre-release* on GitHub so stable users stay on stable releases.

Keep the plain `v<version>` tags: the prerelease scan skips any tag that isn't
valid semver, such as a `desktop-v…` prefix, so beta installs would never update.
Every `v*` release should carry the installer. Builds are currently unsigned, so Windows
SmartScreen shows "Windows protected your PC" on first install (*More info →
Run anyway*). Code signing (e.g. Azure Trusted Signing via electron-builder's
`win.azureSignOptions`) removes that.

### Updating the Python dependencies

The runtime installs exactly what `desktop/requirements.lock.txt` pins. After
changing dependencies in `backend/pyproject.toml`:

```powershell
.\desktop\scripts\build-runtime.ps1 -RefreshLock
```

Commit the regenerated lock. To move to a newer Python, update `$PyVersion`,
`$PbsRelease` and `$PbsSha256` in `build-runtime.ps1` (the checksum comes from the
release's `SHA256SUMS`), then refresh the lock.

## Keeping the website and the desktop app compatible

Both are built from the same code, so a few rules keep the desktop build working:

- **Frontend: nothing that needs a Node server.** No route handlers, middleware,
  server actions, `next/headers`/`cookies()`, or dynamic route segments without
  `generateStaticParams`. `npm run build:desktop` fails loudly if one slips in.
- **Frontend: backend URLs go through `API_BASE` / `apiUrl()`** from
  `src/lib/api.ts`, never `process.env.NEXT_PUBLIC_API_URL` directly.
- **Datetime columns use `UTCDateTime`** (`app/database.py`), not
  `DateTime(timezone=True)`. SQLite has no timezone type.
- **Postgres-only SQL needs a SQLite branch**, like the existing
  `sqlite_insert if dialect == "sqlite" else pg_insert` upserts.
- **Migrations must run on SQLite.** Use `op.batch_alter_table` for anything
  beyond `add_column`/`create_table`. `app/tests/test_alembic_sqlite.py` runs the
  whole chain on SQLite and checks every model column exists afterwards.

## Known limits

- The desktop app and a hosted website keep separate data; they don't sync.
- Inference is CPU-only, since the bundled PyTorch is the CPU build.
- `data/` grows as it does on the server (FITS, images, analysis sessions). Clear
  it from the data folder if disk space matters.
- If port 47800 is taken by another program, the app uses a free port for that
  session. It still works, but browser-stored preferences such as the theme
  don't carry over while it does.
