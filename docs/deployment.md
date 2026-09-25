# Deployment

How to publish this dashboard: what the app needs from its host, which hosting
options fit, and the work that stands between the current dev setup and a public
deployment.

For running it on your own machine, see the
[README quick start](../README.md#quick-start-local-development) — this document
is about putting it on the internet. For a single-user install without a server,
there is also the [Windows desktop app](desktop.md): same backend and UI, but on
SQLite with an in-process cache. The hosted deployment below keeps
Postgres/TimescaleDB and Redis.

---

## 1. What the app needs from a host

These constraints rule out most "deploy in one click" platforms, so they come
first.

**A long-running process, not a request handler.**
[`app/scheduler.py`](../backend/app/scheduler.py) starts an APScheduler instance
inside the backend process with seven recurring jobs: per-source ingestion, event
detection (600 s), radio-burst scanning (`RADIO_BURST_SCAN_INTERVAL`, default
600 s), the radio-burst offline catch-up (`RADIO_BURST_BACKFILL_INTERVAL`,
default 3600 s), CME collection, Kp-forecast detection, and alert dispatch. These
run on their own clock, independent of HTTP traffic. Serverless functions
(Vercel Functions, Netlify, Lambda) have no place to put this.

The catch-up is what makes downtime survivable rather than lossy: on restart it
re-scores the archive days nobody was there to score, so the burst timeline and
the correlation histograms stay continuous. Its work is chunked, committed as it
goes, and resumable, so a deploy in the middle of a long fill costs only the
chunk in flight. It holds a database session per day, not per run.

**Exactly one backend instance.** The scheduler runs *in-process*, so a second
replica duplicates every ingestion job — double-writes, double alerts, double
external API load. Scaling out requires extracting the scheduler into its own
worker process first. Until then, scale up, not out.

**A persistent writable filesystem.** `DATA_DIR` holds downloaded FITS files,
generated spectrograms, solar images, LASCO frames, and Data Analysis session
scratch. Only paths and metadata go in Postgres. A platform with an ephemeral
filesystem loses all of it on every deploy.

**Real memory and disk.** The backend image carries the SunPy/Astropy/reproject
scientific stack, ffmpeg, PyTorch (CPU), and ~214 MB of model checkpoints in
[`backend/ml_model/`](../backend/ml_model) — call it 3–5 GB built. ResNet-18
inference on CPU plus Postgres, Redis, and Next.js alongside it means 8 GB RAM is
comfortable and 4 GB is tight.

**Postgres with TimescaleDB, and Redis.** The compose file pins
`timescale/timescaledb:latest-pg16`. A generic managed Postgres works only if the
TimescaleDB extension is available (Neon and Supabase do not offer it; Timescale
Cloud and self-hosted do).

---

## 2. Hosting options

### Option A — Single VPS with Docker Compose *(recommended)*

One machine runs everything: Postgres, Redis, backend, frontend, and a reverse
proxy terminating TLS.

- **Where**: Hetzner CX42 / DigitalOcean / Linode / Vultr, or any institutional VM.
- **Size**: 4 vCPU, 8 GB RAM, 80–160 GB SSD.
- **Cost**: roughly $25–50/month.
- **TLS**: Caddy is the least work — point a domain at the host and it gets
  Let's Encrypt certificates automatically, no cron renewal to forget.

| | |
|---|---|
| **Good** | Persistent volume is free. Scheduler just runs. Big image is not a problem. Postgres, Redis, and the data dir sit on the same disk, so no egress charges between them. One `docker compose up -d` to deploy. |
| **Bad** | You own the machine: OS patches, backups, disk monitoring, uptime. A single host is a single point of failure. |

**Verdict**: the natural fit. Every constraint in §1 is satisfied by default
rather than worked around.

### Option B — Institutional / university server

Mechanically the same as Option A if Docker is available. Worth preferring when
you have one, because research-network hosting is usually free, has generous
disk, and may already sit behind institutional SSO.

Check before committing: outbound access to NOAA SWPC, e-CALLISTO, Helioviewer,
JSOC, GFZ and SIDC must not be firewalled — the ingestion jobs are useless
without it. Also confirm whether inbound port 80/443 can be opened, or whether
everything must sit behind the campus VPN.

### Option C — Managed split (Vercel + Fly.io/Render + managed data)

Frontend on Vercel, backend on Fly.io or Render with an attached volume,
Postgres on Timescale Cloud, Redis on Upstash.

| | |
|---|---|
| **Good** | No OS to maintain. Frontend gets a global CDN and preview deploys for free. Managed Postgres brings backups and point-in-time recovery. |
| **Bad** | Most moving parts and most expensive (~$50–100/month once the volume and managed database are counted). The backend image is large enough that cold starts and build times hurt. `DATA_DIR` still needs a real volume, so you get the operational burden of a stateful service anyway — without the benefit of it being on the same box as the database. TimescaleDB constrains the database choice. |

**Verdict**: viable, but you pay more to solve problems this app does not have,
and it does not remove the stateful-service work.

### Option D — Object storage for `DATA_DIR` (S3/R2)

Not a hosting option on its own — a modification to any of the above that
replaces the local data directory with object storage. Worth doing *later* if
the data directory outgrows the host disk, or if you ever need more than one
backend instance. It requires reworking every filesystem read/write path in the
services layer, so it is not first-deploy work.

### Ruled out

- **Vercel/Netlify for the backend** — no persistent process, no persistent disk,
  and the deployment size limits are far below what PyTorch plus the checkpoints
  need.
- **Streamlit Community Cloud / Hugging Face Spaces / PythonAnywhere** — wrong
  shape for a Next.js + FastAPI + Postgres + Redis stack.
- **Multi-replica anything** — see the scheduler constraint in §1.

---

## 3. Access model: public read, login for the heavy tools

The dashboard's value is that anyone can look at it, but a handful of endpoints
do real work on demand — they download from external archives, run inference or
ffmpeg, and write to disk. Those are the ones that need a gate. **No
authentication exists in the codebase today**; there is no auth router under
[`backend/app/api/`](../backend/app/api), and every endpoint is currently open.

### Open to everyone (read-only, served from the database and data dir)

`/api/status`, `/api/summary/*`, `/api/goes/*`, `/api/geomagnetic/*`,
`/api/solar-wind/*`, `/api/indices/*`, `/api/forecast/*`, `/api/alerts/*`,
`/api/events`, `/api/solar/images/*`, `/api/soho/lasco/*`, and the read-only
`GET`s under `/api/radio/*`.

Frontend pages: overview, `/xray-proton`, `/geomagnetic`, `/solar-wind`,
`/solar-images`, `/coronagraph`, `/solar-radio`, `/solar-cycle`, `/events`,
`/timeline`, `/forecast`, `/archive`, `/reference`, `/user-guide`.

### Behind a login

| Endpoint | Why |
|---|---|
| `POST /api/analysis/*` — [`routes_data_analysis.py`](../backend/app/api/routes_data_analysis.py) | Fido/JSOC fetches, sequence downloads, J-maps, vector-field prep, ffmpeg movie export. Unbounded external bandwidth and CPU per request. |
| `POST /api/analyzer/*` — [`routes_analyzer.py`](../backend/app/api/routes_analyzer.py) | File uploads, archive pulls, shock fitting. Writes to disk. |
| `POST /api/radio/predict`, `POST /api/radio/ecallisto/process` — [`routes_radio.py`](../backend/app/api/routes_radio.py) | Batch ML inference over a day of segments across stations. |
| `PUT /api/radio/models/default` — [`routes_radio.py:161`](../backend/app/api/routes_radio.py:161) | Changes which classifier the *automatic* scan uses, for everyone, persistently. |
| `POST /api/radio/backfill` — [`routes_radio.py`](../backend/app/api/routes_radio.py) | Starts a long archive re-scoring run (hours of downloads + inference). `force` re-scores days already covered. |
| `PUT /api/notifications/settings`, `POST /api/notifications/test` — [`routes_notifications.py`](../backend/app/api/routes_notifications.py) | Sends real notifications; settings are global. |

Frontend pages: `/data-analysis`, `/e-callisto-analyzer`, `/burst-predictor`,
`/settings`.

### Suggested implementation

For a small number of trusted users, full user management is overkill. In
increasing order of effort:

1. **Reverse-proxy basic auth** on the gated paths. Caddy does this in about six
   lines with bcrypt-hashed passwords in the Caddyfile. Zero application code.
   The catch: the frontend can't tell logged-in from anonymous, so gated pages
   still render and fail at the API call, and the browser credential prompt is
   ugly.
2. **A shared session token** — one FastAPI dependency checking a signed cookie,
   a single `/api/auth/login` route, and a Next.js middleware redirect for the
   four gated pages. A few hundred lines, and the UI can hide what you can't use.
3. **Per-user accounts** with hashed passwords in Postgres. Only worth it if you
   need to attribute analysis sessions to individuals or revoke access per person.

Option 2 is the right level for this app. Whichever you choose, also put a **rate
limit** on the gated endpoints — auth stops strangers, not an authenticated user
who queues fifty movie exports.

---

## 4. Blockers in the current repo

Everything below is dev-oriented and must change before a public deploy.

### 4.1 The frontend has no production build

[`frontend/Dockerfile`](../frontend/Dockerfile) ends in `CMD ["npm", "run", "dev"]`.
Next.js dev mode is slow, leaks source, and is not meant to face the internet.

Needed: a multi-stage Dockerfile that runs `next build` and serves the result,
plus `output: "standalone"` in [`next.config.mjs`](../frontend/next.config.mjs)
so the runtime stage stays small.

### 4.2 `NEXT_PUBLIC_API_URL` is inlined at build time

Next.js substitutes `NEXT_PUBLIC_*` variables into the client bundle during
`next build`. It is read in [`lib/api.ts:89`](../frontend/src/lib/api.ts:89) and
about ten components, every one defaulting to `http://localhost:8000`.

If it is not set **as a build argument** to the public API origin, every visitor's
browser will request data from their own machine and the dashboard will appear
completely empty. Setting it as a runtime environment variable does nothing.

### 4.3 The compose file is a development compose

[`docker-compose.yml`](../docker-compose.yml) is not deployable as-is:

- `./backend:/app` and `./frontend:/app` bind-mount host source over the image,
  so the built image contents are ignored entirely.
- Postgres `5432` and Redis `6379` are published to the host — on a public VM
  these are exposed to the internet.
- The database password is the literal `swdash`.
- `WATCHPACK_POLLING` is dev-only.
- `NEXT_PUBLIC_API_URL: http://localhost:8000` is set as a runtime env var, which
  per §4.2 has no effect on the built frontend.

Needed: a separate `docker-compose.prod.yml` with no bind mounts, no published
database ports, secrets from the environment, and a Caddy service in front.

### 4.4 CORS is localhost-only

`CORS_ORIGINS` defaults to `http://localhost:3000,http://127.0.0.1:3000`
([.env.example:85](../.env.example:85)). It must list the real frontend origin,
and only that.

### 4.5 The data directory grows without bound

Only the analyzer sweeps itself —
[`cleanup_stale(ttl_hours=24)`](../backend/app/services/analyzer_service.py:824).
Nothing prunes `spectra/`, `fits/`, `solar_images/`, or `lasco/`, all of which the
scheduler fills continuously. A local dev tree already reaches ~228 MB; a server
ingesting around the clock fills the disk, and a full disk takes Postgres down
with it.

Needed before launch: a retention job (delete files older than N days, N driven by
how far back the archive pages should reach), plus disk-usage alerting. This is
the item most likely to cause an outage weeks after a successful deploy.

### 4.6 Operational gaps

- **Git LFS on the build host** — run `git lfs install && git lfs pull` before
  building, or the checkpoints copy in as pointer files and burst detection
  silently disables itself with only a log line.
- **Secrets** — `.env` is gitignored, so production values must be provisioned on
  the host. Generate a real Postgres password.
- **Backups** — `pg_dump` on a schedule, off-host. The data directory is
  re-derivable from upstream archives; the database is not.
- **Migrations** — `AUTO_MIGRATE=true` runs `alembic upgrade head` at startup,
  which is convenient but means a bad migration takes the service down on boot.
  Back up before deploying schema changes.
- **Restart policy** — add `restart: unless-stopped` so the stack survives a
  reboot.
- **External API etiquette** — ingestion hits NOAA, e-CALLISTO, Helioviewer, JSOC,
  GFZ and SIDC continuously. Keep the intervals in `.env` conservative; a public
  deployment polling hard is what gets an IP blocked.

---

## 5. Rough order of work

1. Production frontend Dockerfile + `output: "standalone"`. *(§4.1)*
2. `docker-compose.prod.yml` with build args, no bind mounts, no exposed database
   ports, Caddy for TLS. *(§4.3, §4.2)*
3. Domain, DNS, and `CORS_ORIGINS`. *(§4.4)*
4. Data-directory retention job. *(§4.5)*
5. Auth on the gated endpoints and pages, plus rate limiting. *(§3)*
6. Backups, restart policy, disk alerting. *(§4.6)*
7. Deploy, then watch disk and external-API error rates for the first week.

Steps 1–3 get it online. Step 4 keeps it online. Step 5 keeps the bill and the
upstream archives from being someone else's science project.

---

## 6. Reference: services and volumes

From [`docker-compose.yml`](../docker-compose.yml):

| Service | Image / build | Port | Volume |
|---|---|---|---|
| `postgres` | `timescale/timescaledb:latest-pg16` | 5432 | `postgres_data` |
| `redis` | `redis:7-alpine` | 6379 | `redis_data` |
| `backend` | `./backend` (`INSTALL_ML` build arg) | 8000 | `app_data` → `/data` |
| `frontend` | `./frontend` | 3000 | — |

`INSTALL_ML=false` produces a lean backend image without PyTorch — the whole
dashboard works except native radio-burst detection. Useful for a
resource-constrained host, or to get a first deploy up before dealing with the
multi-gigabyte image.

Environment variables are documented inline in [`.env.example`](../.env.example).
The ones that must change for production: `DATABASE_URL` (password),
`CORS_ORIGINS`, `NEXT_PUBLIC_API_URL` (as a *build* arg — see §4.2), and
`ML_INFERENCE_DEVICE=cpu`.

Note that `BACKEND_HOST`, `BACKEND_PORT` and `BACKEND_RELOAD` in
[`.env.example`](../.env.example) are vestigial — nothing in
[`app/config.py`](../backend/app/config.py) reads them, and the container's
`CMD` hard-codes host and port. They are worth deleting so they don't read as
production knobs that do something.
