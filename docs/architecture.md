# Architecture

System architecture of the Space Weather Monitoring Dashboard — how the frontend,
backend, data stores, and external data sources fit together.

> **Status: stub — to be written.**

## Intended sections

- **High-level diagram** — frontend (Next.js) → backend (FastAPI) → PostgreSQL/
  TimescaleDB + Redis → external sources (NOAA SWPC, SDO, SOHO/LASCO, e-CALLISTO).
- **Backend layering** — `api/` (thin routes) → `services/` (domain logic) →
  `collectors/` (data fetch) → `processing/` (reusable functions); `schemas/`
  (Pydantic), `models/` (ORM).
- **Data flow** — scheduled ingestion vs. on-request live fallback (see
  [persistence-phase.md](persistence-phase.md)).
- **Storage strategy** — time-series in TimescaleDB hypertables; large files (FITS,
  spectrograms, images, LASCO frames) under `DATA_DIR`, metadata in the DB.
- **Caching** — Redis layer in front of live fetches and DB reads.
- **Deployment topology** — Docker Compose services and their networking (see
  [deployment.md](deployment.md)).
