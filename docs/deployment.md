# Deployment

How to run the dashboard locally and deploy it — Docker Compose services, environment
variables, and volumes.

> **Status: stub — to be written.**

## Intended sections

- **Local development** — running backend (`uvicorn`) and frontend (`npm run dev`)
  directly; see the [README quick start](../README.md#quick-start-local-development).
- **Docker Compose** — services in `../docker-compose.yml` (postgres/TimescaleDB,
  redis, backend, frontend), ports, healthchecks, and named volumes
  (`postgres_data`, `redis_data`, `app_data`).
- **Environment variables** — derived from `../.env.example`: `DATABASE_URL`,
  `REDIS_URL`, `DATA_DIR`, `NOAA_BASE_URL`, `CORS_ORIGINS`, `NEXT_PUBLIC_API_URL`.
- **Database migrations** — running Alembic migrations + TimescaleDB hypertable
  creation on first deploy (see [persistence-phase.md](persistence-phase.md), Step 0).
- **Data directory** — `DATA_DIR` layout (`fits/`, `spectra/`, `solar_images/`,
  `lasco/`) and persistence considerations.
- **Production notes** — build images, scheduler/ingestion process, backups, scaling.
