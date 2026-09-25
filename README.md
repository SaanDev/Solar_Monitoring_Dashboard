# Space Weather Monitoring Dashboard

A web-based dashboard for monitoring and analyzing space-weather parameters, with a focus on e-CALLISTO solar radio dynamic spectra and event-centered space-weather interpretation.

## Features

- e-CALLISTO solar radio burst dynamic spectra (FITS processing)
- GOES XRS X-ray flux (dual channel, log scale, flare-class labels)
- GOES proton flux (multiple energy channels)
- SDO/AIA and HMI solar images
- SOHO/LASCO C2/C3 coronagraph images and short movie previews
- Dst and Kp geomagnetic indices
- Solar wind and IMF parameters
- Event alerts and combined event timeline
- Archive search

## Stack

- **Frontend**: Next.js 14, TypeScript, Tailwind CSS, Plotly.js, SWR, ShadCN UI
- **Backend**: FastAPI, Python 3.11+, Pydantic v2, Astropy, NumPy, SciPy, Pandas
- **Database**: PostgreSQL (TimescaleDB)
- **Cache**: Redis
- **Deployment**: Docker Compose

## Quick start (local development)

### Prerequisites

- Python 3.11+
- Node.js 20+
- Docker + Docker Compose
- [Git LFS](https://git-lfs.com) — the radio-burst ML checkpoint (~128 MB) is
  stored in the repo via LFS. Install it **before** cloning (or run
  `git lfs install && git lfs pull` after) so `backend/ml_model/best.pt` is
  fetched as the real file rather than a pointer.

### 1. Environment

```bash
cp .env.example .env
# Edit .env as needed
```

### 2. Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
uvicorn app.main:app --reload --port 8000
```

### 3. Frontend

```bash
cd frontend
npm install
npm run dev
```

Open [http://localhost:3000](http://localhost:3000).

### 4. Database + Redis (Docker)

```bash
docker compose up postgres redis
```

### 5. Radio-burst ML models (native inference)

The solar radio-burst classifiers (ResNet-18) run **natively inside the backend**
— no separate microservice. Three checkpoints ship in the repo via Git LFS under
`backend/ml_model/`:

| Model | File | Task | Notes |
|---|---|---|---|
| **CCM v1.0.0** | `best.pt` | burst / no-burst | The original classifier. Threshold 0.595. Unchanged — kept selectable so past results stay comparable. |
| **CCM v1.1.0** | `ccm_v1_1_0.pt` | burst / no-burst | Retrained. Threshold 0.51, validation F1 0.920, test F1 0.932. **Default.** |
| **CCMT v1.0.0** | `ccmt_v1_0_0.pt` | burst type | 3-class (Type II / Type III / Other), validation accuracy 0.966, macro-F1 0.889. Runs only on segments a CCM model flagged as a burst. |

```bash
# One-time per machine, then fetch the checkpoints:
git lfs install
git lfs pull

# Install the PyTorch dependencies (CPU/CUDA/Apple-Silicon MPS auto-detected):
cd backend
pip install -e ".[ml]"
```

Which model the *automatic* scan uses is chosen from the dashboard's **Settings**
page (Automatic Burst Detection) — stored in the database, applied to the running
scanner, and preserved across restarts. `RADIO_BURST_BINARY_MODEL` /
`RADIO_BURST_CLASSIFY_TYPES` remain the defaults until something is chosen there.
The Burst Detector page still lets you pick per run. `GET /api/radio/models` lists
what is available and `PUT /api/radio/models/default` sets the scan's model;
`app/ml/registry.py` is the single source of truth for model ids and paths.

Switching models is safe: detections are deduped *per model*, so the next scan
re-scores the recent window with the new classifier and rebuilds the burst events
from it, each model gating alerts on its own tuned threshold.

The scan only looks at the last `RADIO_BURST_MAX_AGE_HOURS`, so downtime would
otherwise leave permanent holes in the burst timeline and the correlation
histograms. An **offline catch-up** closes them: it compares the archive listing
against what has been scored and fills in the missing days, automatically (the
last `RADIO_BURST_BACKFILL_MAX_DAYS`, re-checked hourly) or on demand from
Settings → Detection Coverage, which also shows per-day coverage and lets a run
be aimed at an older range. Runs are resumable and cancellable, a day covered by
*any* model counts as covered, and filled-in events never send notifications —
see [`app/services/radio_backfill_service.py`](backend/app/services/radio_backfill_service.py).

CCMT is a *classifier*, not a detector: it was trained on hand-drawn crops around
individual bursts, so the cascade finds bright connected regions inside a
burst-positive segment, crops each, and classifies the crops. Regions smaller
than CCMT's training distribution are discarded rather than guessed at, so a
burst may legitimately come back untyped. Treat types as estimates.

On Apple Silicon Macs, PyTorch automatically uses the MPS backend. Models are
loaded once at startup; a missing checkpoint or missing PyTorch is non-fatal —
that model is simply unavailable and logged.

**Adding a retrained checkpoint.** Trainer `best.pt` files carry optimizer state
(~128 MB). `scripts/repack_model.py` strips it down to `{model_state, config}`
(~43 MB), which is all the loader reads, and prints the architecture, threshold
and class map so the right run can be confirmed before committing:

```bash
python scripts/repack_model.py --all
```

## Full stack with Docker

```bash
docker compose up
```

All services start: PostgreSQL on 5432, Redis on 6379, backend on 8000, frontend on 3000.

## Desktop app (Windows and Linux)

The same dashboard also ships as an installable desktop app for Windows (an
installer) and Linux (a `.deb` for Ubuntu, Debian and derivatives): no Docker,
Postgres, Redis, Python or Node needed on the target machine. It runs the
backend on a local SQLite database, serves the UI itself, and keeps collecting
data and raising alerts from the system tray. Packages are published on the
[Releases page](https://github.com/SaanDev/Solar_Monitoring_Dashboard/releases)
and the installed app updates itself. On Linux, install with
`sudo apt install ./SolarMonitoringDashboard-<version>-amd64.deb`.

Build one locally with `.\desktop\scripts\build.ps1` (Windows) or
`./desktop/scripts/build.sh` (Linux). See [docs/desktop.md](docs/desktop.md) for
how it works, where it keeps its data, and how to cut a release.

## API

- `GET /api/status` — backend health
- `GET /api/summary/latest` — latest values for overview cards
- `GET /api/goes/xrs?start=&end=` — GOES XRS flux
- `GET /api/goes/proton?start=&end=` — GOES proton flux
- `GET /api/geomagnetic/kp?start=&end=` — Kp index
- `GET /api/geomagnetic/dst?start=&end=` — Dst index
- `GET /api/solar/images/latest` — latest solar images
- `GET /api/soho/lasco/latest?camera=C2` — latest LASCO images
- `GET /api/radio/stations` — e-CALLISTO station list
- `POST /api/radio/ecallisto/process` — process a FITS file
- `GET /api/radio/backfill` — burst-detection coverage per day + catch-up progress
- `POST /api/radio/backfill` — fill in days missed while offline
- `GET /api/alerts/latest` — latest alerts
- `GET /api/events?start=&end=` — event timeline

## Data storage

Large files (FITS, spectrograms, solar images, LASCO frames) are stored under `DATA_DIR` (default `/data`), not in the database. Only metadata and file paths are stored in PostgreSQL.

## Docs

- [Architecture](docs/architecture.md)
- [API design](docs/api-design.md)
- [Data sources](docs/data-sources.md)
- [Deployment](docs/deployment.md)
- [Desktop app (Windows and Linux)](docs/desktop.md)
