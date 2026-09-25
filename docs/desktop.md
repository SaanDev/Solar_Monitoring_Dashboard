# Desktop app (Windows and Linux)

The dashboard ships as an installable desktop app alongside the website: a
Windows installer and a Linux `.deb` package. It is the same backend and the
same UI, packaged so that a single installer is all a machine needs: no Docker,
Postgres, Redis, Python or Node.

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

Linux is laid out the same way: the app lives in `/opt/Solar Monitoring Dashboard`,
the interpreter is `resources/python/bin/python3`, and the data folder is
`~/.local/share/SolarDashboard`.

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
  [`desktop/requirements.lock.txt`](../desktop/requirements.lock.txt) (Windows) or
  [`desktop/requirements-linux.lock.txt`](../desktop/requirements-linux.lock.txt)
  (Linux). The Linux lock pins every package the two share to the Windows
  version, so both builds ship the same stack. It includes CPU-only PyTorch, so
  every feature works, including burst detection. There's no PyInstaller
  freezing, so the bundle behaves like a normal install.

Closing the window hides it to the **system tray**. Ingestion, the radio-burst
scan, the offline catch-up and alert delivery keep running, and new
warning/critical alerts appear as desktop notifications. Quit from the tray menu.

On Linux the tray icon needs a desktop that shows tray (AppIndicator /
StatusNotifier) icons. Ubuntu, KDE Plasma, Cinnamon and Xfce do; stock GNOME
needs the *AppIndicator and KStatusNotifierItem Support* extension. Without one,
the app still runs in the background: open it again from the app launcher, and
quit with <kbd>Ctrl</kbd>+<kbd>Q</kbd> in its window.

## Where things live

| What | Windows | Linux |
|---|---|---|
| App | `%LOCALAPPDATA%\Programs\Solar Monitoring Dashboard` (per-user, no admin) | `/opt/Solar Monitoring Dashboard`, command `solar-monitoring-dashboard` |
| Data folder | `%LOCALAPPDATA%\SolarDashboard` | `~/.local/share/SolarDashboard` |
| Database | `dashboard.db` in the data folder | same |
| Downloaded data, analysis sessions | `data` in the data folder | same |
| Logs (`backend.log`, `main.log`, `backend-console.log`) | `logs` in the data folder | same |
| User settings (`.env`) | `.env` in the data folder (tray → *Edit settings*) | same; opens in your default text editor |
| Window state, browser storage | `electron` in the data folder | same |
| Start at login | Windows login item (tray → *Start with Windows*) | `~/.config/autostart/solar-monitoring-dashboard.desktop` (tray → *Start at login*) |

On Linux, `~/.local/share` and `~/.config` follow `$XDG_DATA_HOME` and
`$XDG_CONFIG_HOME` when those are set.

The `.env` accepts any setting from [`.env.example`](../.env.example), for example
`JSOC_EMAIL` or `TELEGRAM_BOT_TOKEN`. After editing it, use tray → *Restart
backend*. The database, data folder, port and CORS are managed by the app.

**Reset:** quit the app and delete the data folder. Uninstalling on Windows asks
whether to delete it too. Removing the Linux package never touches it, since a
system package doesn't delete users' files. Updates never touch it on either
platform.

## Installing on Linux

Download `SolarMonitoringDashboard-<version>-amd64.deb` from the
[Releases page](https://github.com/SaanDev/Solar_Monitoring_Dashboard/releases)
and install it with apt, which also pulls in the few system libraries Electron
needs:

```bash
sudo apt install ./SolarMonitoringDashboard-1.0.0-beta-amd64.deb
```

It appears in the app launcher as *Solar Monitoring Dashboard*; from a terminal,
run `solar-monitoring-dashboard`. It needs 64-bit Ubuntu 22.04 or Debian 12 or
newer, or a derivative such as Linux Mint or Pop!_OS. Remove it with
`sudo apt remove solar-monitoring-dashboard`.

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

### Building the Linux package

Prerequisites: Linux x86_64 (WSL 2 with Ubuntu works), Node 20+, `curl`, and Git
LFS with the checkpoints pulled. No Python is needed; the build downloads its own.

```bash
./desktop/scripts/build.sh
```

It runs the same steps as the Windows build. `build-runtime.sh` stages and
smoke-tests the runtime (cached in `desktop/build/cache`), the static UI is
built, and electron-builder writes
`desktop/dist/SolarMonitoringDashboard-<version>-amd64.deb` and
`latest-linux.yml`. `--skip-runtime` reuses the staged runtime. The same caution
about `next dev` applies.

To check a package the way CI does (install it with apt, start it headless,
quit, remove it), run the test script. It needs sudo and uses a throwaway home
folder:

```bash
./desktop/scripts/test-deb.sh desktop/dist/SolarMonitoringDashboard-*-amd64.deb
```

Build on the oldest Linux you want to support, because pip picks wheels for the
build machine's glibc. CI builds on Ubuntu 22.04.

### Running the shell from source

```powershell
npm --prefix frontend run build:desktop   # static UI -> frontend/out
cd desktop
npm install
npm start                                 # uses backend/.venv and frontend/out
```

In dev, the shell uses `backend/.venv/Scripts/python.exe` (`backend/.venv/bin/python`
on Linux). That venv needs the `desktop` extra (`pip install -e ".[desktop]"`, for `aiosqlite`). Override the
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
   first creates the **draft** release `v1.0.0-beta`, and fails if the tag and
   `package.json` disagree. Two jobs then run in parallel, each building its
   runtime and running the backend test suite on it:
   - **Windows** builds the installer and uploads it, with `latest.yml`, to the draft.
   - **Linux** builds the `.deb` and uploads it, with `latest-linux.yml`, to the
     same draft. It then installs the package, launches it headless and removes
     it again (`test-deb.sh`).

   Betas use `latest.yml` / `latest-linux.yml` too: a beta install first asks for
   `beta.yml` (`beta-linux.yml`), then falls back to it.
4. Review the draft on GitHub and **publish** it once both jobs are green.
   Installed apps check for updates at startup and every 6 hours, download the
   update in the background, and offer to restart. On Linux, installing it asks
   for the user's password, since the package is installed system-wide.
   Declining or cancelling keeps the current version running; it's offered again
   on the next check.

How installed apps find updates:

- **A prerelease install** (such as `1.0.0-beta`) scans every published release,
  newest first, and takes the first one with a semver tag. This covers later
  betas and the final `1.0.0`.
- **A stable install** only follows the release GitHub marks as **Latest**. Mark
  betas as *pre-release* on GitHub so stable users stay on stable releases.

Keep the plain `v<version>` tags: the prerelease scan skips any tag that isn't
valid semver, such as a `desktop-v…` prefix, so beta installs would never update.
Every `v*` release should carry both packages. Builds are currently unsigned, so Windows
SmartScreen shows "Windows protected your PC" on first install (*More info →
Run anyway*). Code signing (e.g. Azure Trusted Signing via electron-builder's
`win.azureSignOptions`) removes that.

### Updating the Python dependencies

The runtimes install exactly what the locks pin: `desktop/requirements.lock.txt`
(Windows) and `desktop/requirements-linux.lock.txt` (Linux). After changing
dependencies in `backend/pyproject.toml`, refresh the Windows lock first, then
the Linux one, which pins every shared package to the Windows version:

```powershell
.\desktop\scripts\build-runtime.ps1 -RefreshLock     # on Windows
```

```bash
./desktop/scripts/build-runtime.sh --refresh-lock     # on Linux or WSL
```

Commit both locks. To move to a newer Python, update `$PyVersion`, `$PbsRelease`
and `$PbsSha256` in `build-runtime.ps1`, and `PY_VERSION`, `PBS_RELEASE` and
`PBS_SHA256` in `build-runtime.sh`. The checksums come from the release's
`SHA256SUMS`; Linux uses the `x86_64-unknown-linux-gnu-install_only_stripped`
archive. Then refresh both locks.

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
- Linux: only a `.deb` for x64 (Debian, Ubuntu and derivatives). There's no
  AppImage, RPM or ARM build yet.
- Inference is CPU-only, since the bundled PyTorch is the CPU build.
- `data/` grows as it does on the server (FITS, images, analysis sessions). Clear
  it from the data folder if disk space matters.
- If port 47800 is taken by another program, the app uses a free port for that
  session. It still works, but browser-stored preferences such as the theme
  don't carry over while it does.
