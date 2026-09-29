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
- [Git LFS](https://git-lfs.com) — the radio-burst ML checkpoint (~43 MB) is
  stored in the repo via LFS. Install it **before** cloning (or run
  `git lfs install && git lfs pull` after) so `backend/ml_model/ccm_v2_0.pt` is
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

### 5. Radio-burst ML model (native inference)

The solar radio-burst model runs **natively inside the backend** — no separate
microservice. One checkpoint ships in the repo via Git LFS:

| Model | File | Task | Notes |
|---|---|---|---|
| **CCM v2.0** | `backend/ml_model/ccm_v2_0.pt` | burst detection **and** type | Unified region model: No_Burst / RFI / Type II / Type III / Type IIIG / Other. Calibrated threshold 0.798 (≈5% of quiet files flagged, ≈66% of burst files found on validation); validation region accuracy 0.968, macro-F1 0.839. |

It replaced CCM v1.0.0 / v1.1.0 (binary burst / no-burst) and CCMT v1.0.0 (burst
type). The exported bundle it came from — model card, training config and a
standalone `predict.py` — is kept alongside in `backend/ml_model/ccm_v2_0/`
(its full-size weights are git-ignored).

```bash
# One-time per machine, then fetch the checkpoint:
git lfs install
git lfs pull

# Install the PyTorch dependencies (CPU/CUDA/Apple-Silicon MPS auto-detected):
cd backend
pip install -e ".[ml]"
```

The model works on regions, as it was trained: each segment is normalized as a
whole, bright candidate regions are located, and every region is scored from
three 224×224 views (the region, a wide full-band strip around it, and that strip
on a quiet-part background) plus 28 measured drift and interference features. A
region is a burst when its burst evidence — one minus P(No_Burst) minus P(RFI) —
reaches the calibrated threshold; a segment is a burst when any region is, and
takes the type of its largest burst region. **Type IIIG (a group of Type III
bursts) is reported as Type III**: the two probabilities are added before the
type is chosen. The region finder's settings, the threshold and the
type-frequency correction all come from the checkpoint, which was calibrated with
them. The port in `backend/app/ml/` reproduces the CALLISTO Trainer's
`CascadePredictor` bit for bit (`app/tests/test_ml_unified.py` pins golden values).

`GET /api/radio/models` lists what is available and `PUT /api/radio/models/default`
sets the scan's model (Settings → Automatic Burst Detection, stored in the
database); `RADIO_BURST_MODEL` is the default until something is chosen there, and
`app/ml/registry.py` is the single source of truth for model ids and paths.
Detections are deduped *per model*, so after a model change the next scan
re-scores the recent window, and stored rows from a retired model keep being
judged by that model's own threshold until they are re-scored.

The scan only looks at the last `RADIO_BURST_MAX_AGE_HOURS`, so downtime would
otherwise leave permanent holes in the burst timeline and the correlation
histograms. An **offline catch-up** closes them: it compares the archive listing
against what has been scored and fills in the missing days, automatically (the
last `RADIO_BURST_BACKFILL_MAX_DAYS`, re-checked hourly) or on demand from
Settings → Detection Coverage, which also shows per-day coverage and lets a run
be aimed at an older range. Runs are resumable and cancellable, and filled-in
events never send notifications. Coverage is kept *per model*, so a model change
re-scores the whole automatic window with the new model, newest day first — about
an hour of CPU per archive day with CCM v2.0 — see
[`app/services/radio_backfill_service.py`](backend/app/services/radio_backfill_service.py).

On Apple Silicon Macs, PyTorch automatically uses the MPS backend. Models are
loaded once at startup; a missing checkpoint or missing PyTorch is non-fatal —
the model is simply unavailable and logged.

**Adding a retrained checkpoint.** Trainer `best.pt` files carry optimizer state
(~128 MB). `scripts/repack_model.py` strips it down to `{model_state, config}`
(~43 MB), which is all the loader reads, and prints the architecture, views,
feature set, calibrated threshold and class map so the right run can be confirmed
before committing (run it with a Python that has torch, e.g. the Trainer's venv):

```bash
python scripts/repack_model.py --all
```

## Full stack with Docker

```bash
docker compose up
```

All services start: PostgreSQL on 5432, Redis on 6379, backend on 8000, frontend on 3000.

<<<<<<< HEAD
## Desktop app (Windows)

The same dashboard also ships as an installable Windows app: one installer, no
Docker, Postgres, Redis, Python or Node needed on the target machine. It runs the
backend on a local SQLite database, serves the UI itself, and keeps collecting
data and raising alerts from the system tray. Installers are published on the
[Releases page](https://github.com/SaanDev/Solar_Monitoring_Dashboard/releases)
and the installed app updates itself.

Build one locally with `.\desktop\scripts\build.ps1`. See
[docs/desktop.md](docs/desktop.md) for how it works, where it keeps its data, and
how to cut a release.
=======
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
>>>>>>> d325f0ffea140b14d8efde51c7c0cf3c0712f39b

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
<<<<<<< HEAD
- [Desktop app (Windows)](docs/desktop.md)
=======
- [Desktop app (Windows and Linux)](docs/desktop.md)
>>>>>>> d325f0ffea140b14d8efde51c7c0cf3c0712f39b
