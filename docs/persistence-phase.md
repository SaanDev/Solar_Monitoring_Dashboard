# Persistence & Ingestion Phase

## Overview

Today the backend fetches every data product **live from NOAA / e-CALLISTO on each
request** and never stores it. This phase moves the dashboard to **scheduled
ingestion into TimescaleDB**, **Redis-cached reads**, and a **working Archive**,
while keeping a **live-fetch fallback** so the dashboard never goes blank on a cold
database.

Goal in one line: *collect once on a schedule, store in TimescaleDB, serve from the
DB through Redis, fall back to live only when the DB has a gap.*

## Why now (current state)

The backend has a rich, working surface (FastAPI routes, processing modules, a real
Next.js frontend, tests), but the **data layer is designed yet unwired**:

- `apscheduler` is a declared dependency (`../backend/pyproject.toml`) but **nothing
  schedules the collectors**.
- `../backend/app/database.py` defines an async engine + `Base`, but
  `../backend/app/models/` is empty (no ORM tables) and **no service queries the
  DB** — every service fetches live per request (e.g.
  `../backend/app/services/goes_xrs_service.py`,
  `../backend/app/services/kp_service.py`).
- Redis is in `../docker-compose.yml` but the app never uses it; the only caching is
  in-memory module dicts (e.g. `_meta_cache` in
  `../backend/app/services/ecallisto_service.py`), lost on restart.

Consequences:

- The **Archive page is a `"coming soon"` stub** (`../frontend/src/app/archive/page.tsx`)
  because there is no stored history to search.
- History is capped at NOAA's rolling 6h–7d windows.
- Every request re-hits external sources (slow, fragile, rate-limit-prone).

All needed dependencies are already present (`sqlalchemy[asyncio]`, `asyncpg`,
`alembic`, `redis`, `apscheduler`) and the Postgres image is **TimescaleDB**
(`timescale/timescaledb:latest-pg16`). This phase is **pure wiring — no new
infrastructure**.

## Design principles

Carried over from `../AGENT_RULES.md`:

- UTC everywhere; **preserve original source timestamps**.
- Store the **`source` name + `ingested_at`** with every record.
- **Never silently mix** real-time / provisional / final values — carry a
  `quality`/`source` flag through to the API response.
- Keep large files out of Git; processed products live under `DATA_DIR`, only
  **metadata + file paths** go in the DB.
- **Idempotent ingestion** — re-running a collector must not create duplicate rows.

---

## Wave 1 — Numeric time-series (GOES XRS, GOES proton, Kp, Dst)

This wave changes **no response models**, so the **frontend needs no changes**.

### Step 0 — Schema + Alembic

- Add ORM models in `../backend/app/models/`:
  - `goes_xrs` — `time`, `satellite`, `short_channel`, `long_channel`
  - `goes_proton` — `time`, `satellite`, `flux_gt10`, `flux_gt50`, `flux_gt100`
  - `kp_index` — `time`, `kp`
  - `dst_index` — `time`, `dst`
  - `source_status` — `name` (PK), `last_success_at`, `last_error`, `status`
- Column shapes mirror the existing Pydantic schemas in
  `../backend/app/schemas/goes_schema.py` and
  `../backend/app/schemas/geomagnetic_schema.py` — keep them aligned so mapping is 1:1.
- **Primary key `(time, source)`** on each time-series table for upsert idempotency.
- Set up Alembic (`alembic init`), write the initial migration to create the tables,
  then run raw SQL per time-series table:
  `SELECT create_hypertable('<table>', 'time');` (TimescaleDB).
- **Decision: Alembic over `Base.metadata.create_all`** — hypertables need raw SQL in
  a migration anyway, and versioned migrations are wanted for a DB-backed service.

### Step 1 — Redis cache helper

- New `../backend/app/cache.py` using `redis.asyncio`, pointed at `settings.redis_url`.
- Minimal surface: `cache_get_json(key)` / `cache_set_json(key, value, ttl)`.
- Used to wrap latest/range responses (short TTLs: latest ~30–60s, range ~5 min).
- Replaces the in-memory module dicts so caching survives restarts and is shared
  across workers.

### Step 2 — Ingestion + scheduler

- Refactor collectors (`../backend/app/collectors/collect_*.py`) to *fetch → parse →
  upsert* using `INSERT ... ON CONFLICT (time, source) DO UPDATE`. The existing
  `fetch_*` / `parse_*` functions stay as-is; add a thin ingest wrapper that persists
  their parsed output.
- Start an APScheduler `AsyncIOScheduler` in `../backend/app/main.py`'s `lifespan`:
  - GOES XRS / proton: every ~1–5 min
  - Kp / Dst: hourly
  - Run each job **once on startup** to warm the DB.
- Each job records success/error into `source_status`.
- Rewrite `/api/sources/status` (`../backend/app/api/routes_status.py`) to report the
  real `last_updated` from `source_status` instead of the current hard-coded
  `"unknown"`.

### Step 3 — Services read from DB, with live fallback + cache

- `get_goes_xrs(start, end)` & the equivalent proton/Kp/Dst service functions query
  the DB for the requested range, wrapped in the Redis cache.
- On a gap (cold start, or scheduler hasn't run yet), **fall back to the existing live
  fetch and backfill** the DB, then return.
- Keep the `source`/`quality` flag on returned points so real-time vs provisional is
  never silently merged.
- Response models unchanged → **no frontend changes for Wave 1**.

---

## Wave 2 — Archive (file / metadata products)

### Step 4 — Archive metadata + endpoint + UI

- Add metadata tables for the **file-based** products — e-CALLISTO spectra and LASCO
  frames: `path` (under `DATA_DIR`), `source`, `instrument`, `station`/`wavelength`,
  `start_time`, `end_time`, `processing_method`/params.
- Write metadata when each product is rendered — hook into `_render_archive_file` in
  `../backend/app/services/ecallisto_service.py` and the LASCO service.
- Add `GET /api/archive?start=&end=&type=` querying this metadata.
- Replace the `"coming soon"` stub in `../frontend/src/app/archive/page.tsx` with a
  real search UI (reuse existing card/grid components; add the API call in
  `../frontend/src/lib/api.ts`).

> **Open question — solar-image archiving (decide before building it).**
> Solar images are *pointers* to upstream `latest` URLs that overwrite
> (`../backend/app/services/solar_image_service.py`). A true solar-image archive
> requires periodically **downloading + storing snapshots** (storage cost) rather
> than recording pointers that immediately go stale. Resolve this trade-off first;
> e-CALLISTO / LASCO (already downloaded to `DATA_DIR`) come first regardless.

### Step 5 — Tests + verification

- Add tests in `../backend/app/tests/` (follow the pattern in `test_goes.py`):
  - upsert idempotency (double-insert → exactly one row),
  - DB range query returns the right window,
  - cache hit/miss,
  - live-fallback path when the DB is empty.
- End-to-end:
  1. `docker compose up postgres redis`
  2. Run the backend; confirm the scheduler populates tables (`psql` row counts).
  3. `GET /api/sources/status` shows real `last_updated` timestamps.
  4. Range endpoints return DB-backed data; cold-start still works via fallback.
  5. The Archive page lists rendered products.

---

## Suggested execution order

Commit after each step so progress survives the Windows ↔ MacBook switch via
`git pull`:

1. Step 0 — schema + Alembic
2. Step 1 — Redis cache helper
3. Step 2 — ingestion + scheduler + real `sources/status`
4. Step 3 — services read-from-DB + live fallback
5. Step 4 — archive metadata + endpoint + UI
6. Step 5 — tests

Wave 1 (Steps 0–3) is independently shippable and delivers most of the value (real
history + speed + reliable source health). Wave 2 (Steps 4–5) lights up the Archive.
