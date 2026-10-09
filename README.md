# Space Weather Monitoring Dashboard

A web-based dashboard for monitoring and analyzing space-weather parameters, with a focus on e-CALLISTO solar radio dynamic spectra and event-centered space-weather interpretation.

**Current version: 1.1.0-beta** — see the
[Releases page](https://github.com/SaanDev/Solar_Monitoring_Dashboard/releases)
for the desktop installers.

## What's new in 1.1.0-beta

- **Linux desktop app.** A `.deb` for Ubuntu, Debian and derivatives now ships
  alongside the Windows installer, with start-at-login on both.
- **New burst detection model.** Radio bursts are detected with BnB v1.1, a
  whole-file burst / no-burst model (see
  [Radio-burst ML model](#5-radio-burst-ml-model-native-inference)). It doesn't
  type bursts, so type fields stay empty for new detections.
- **Meaningful Active Alerts count.** The Overview card counts only alerts for
  events in progress or that subsided in the last 6 hours, instead of the whole
  alert history. Its color follows the most severe one, and a caption breaks it
  down by type.
- **Cleaner event history.** A long storm or proton event is stored as one event
  instead of a new fragment on every detection pass, and events left "in
  progress" by downtime are closed. On the first start after upgrading, stored
  flares, proton events and storms are re-derived once from the time-series,
  which also drops events left behind by data corrected upstream.
- **Timeline fix.** The GOES X-ray chart in the event inspector fills its panel
  next to the dynamic spectrum.
- **Desktop fix.** A development run uses its own Windows app identity, so it no
  longer replaces the installed app's taskbar icon.

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
- [Git LFS](https://git-lfs.com) — the radio-burst ML checkpoint (~81 MB) is
  stored in the repo via LFS. Install it **before** cloning (or run
  `git lfs install && git lfs pull` after) so `backend/ml_model/bnb_v1_1.pt` is
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
| **BnB v1.1** | `backend/ml_model/bnb_v1_1.pt` | burst / no-burst | Whole-file ResNet-34 with a station / frequency / date metadata branch, trained on 2026 recordings. Threshold 0.787, tuned on the validation split: precision 0.986, recall 0.921, 1.0% of quiet files flagged; on the held-out test split precision 0.973, recall 0.855, 1.5% of quiet files flagged. Does not type bursts. |

It replaced BnB v1.0 (the same network; threshold 0.563), which had replaced
CCM v2.0 (a region model that also typed bursts, set aside until it is
retrained), and before it CCM v1.0.0 / v1.1.0 and CCMT v1.0.0. The exported
bundle BnB v1.1 came from — model card, training config and a standalone
`predict.py` — is kept alongside in `backend/ml_model/bnb-v1.1/` (its full-size
weights are git-ignored; `checkpoint.pt` is over GitHub's 100 MB limit, so
`scripts/repack_model.py` slims it to the file the backend loads). Note that the
bundle's `predict.py` does not pass the metadata input this model needs, so it
fails as exported; the backend builds that input itself.

```bash
# One-time per machine, then fetch the checkpoint:
git lfs install
git lfs pull

# Install the PyTorch dependencies (CPU/CUDA/Apple-Silicon MPS auto-detected):
cd backend
pip install -e ".[ml]"
```

The model scores whole segments, as it was trained: each segment's spectrum is
cleaned, each channel's median over the whole file is subtracted as background,
the result is scaled to Plotutil dB, windowed to [-1, 8] dB and resized to
224×224. A metadata vector — the station's index among the 50 trained stations
(0 for any other), the frequency range and the date — joins the image features
before one burst probability; the segment is a burst when it reaches the
threshold stored in the checkpoint. Burst types are not reported: the type fields
stay empty, and the UI shows type information only for rows a typing model
stored. The port in `backend/app/ml/` matches the CALLISTO Trainer on synthetic
golden files (`app/tests/bnb_cases.py`) and on real files.

On held-out files the model was never trained on, it flags 57% of labelled
bursts (BnB v1.0: 61%) and 7.6% of quiet files (v1.0: 8.1%). Stations outside its
50 flag more quiet files (10% against 7%), mostly from a few cluttered stations
(INDIA-OOTY, MEXICO-LANCE, MEXART, ...). The station input itself barely matters
(about 0.004 on the probability), so those stations are scored as the Trainer
would; the multi-station confirmation keeps their
false alarms out of the alerts: a burst is an event only when reliable stations at
independent sites agree on it beyond chance (see
[docs/radio-burst-confirmation.md](docs/radio-burst-confirmation.md)).

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
a few minutes of CPU per archive day with BnB v1.1, plus the downloads — see
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
- `GET /api/summary/latest` — latest values for overview cards, including the
  active-alert count, its highest severity and a count per event type
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
- `GET /api/alerts/latest` — the full alert history, newest first
- `GET /api/events?start=&end=` — event timeline

## Data storage

Large files (FITS, spectrograms, solar images, LASCO frames) are stored under `DATA_DIR` (default `/data`), not in the database. Only metadata and file paths are stored in PostgreSQL.

## Docs

- [Architecture](docs/architecture.md)
- [API design](docs/api-design.md)
- [Data sources](docs/data-sources.md)
- [Deployment](docs/deployment.md)
- [Desktop app (Windows and Linux)](docs/desktop.md)
