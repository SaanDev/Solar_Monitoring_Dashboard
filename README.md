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

## Full stack with Docker

```bash
docker compose up
```

All services start: PostgreSQL on 5432, Redis on 6379, backend on 8000, frontend on 3000.

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
- `GET /api/alerts/latest` — latest alerts
- `GET /api/events?start=&end=` — event timeline

## Data storage

Large files (FITS, spectrograms, solar images, LASCO frames) are stored under `DATA_DIR` (default `/data`), not in the database. Only metadata and file paths are stored in PostgreSQL.

## Docs

- [Architecture](docs/architecture.md)
- [API design](docs/api-design.md)
- [Data sources](docs/data-sources.md)
- [Deployment](docs/deployment.md)
