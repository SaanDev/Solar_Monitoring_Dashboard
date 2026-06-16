# API Design

Conventions and contract for the backend REST API served by FastAPI under `/api`.

> **Status: stub — to be written.**

## Intended sections

- **Conventions** — UTC ISO-8601 timestamps, range query params (`start`, `end`),
  the 7-day max range rule (see `backend/app/api/routes_goes.py`), error shapes.
- **Endpoint reference** — group by domain (status, summary, goes, geomagnetic,
  solar images, soho/lasco, radio, alerts, events, archive). The current list lives
  in the [README](../README.md#api); expand each with params + response schema.
- **Response models** — link each endpoint to its Pydantic schema in
  `backend/app/schemas/`.
- **Data quality flags** — how real-time / provisional / final are signalled (per
  `AGENT_RULES.md`).
- **Source health** — `/api/sources/status` contract (see
  [persistence-phase.md](persistence-phase.md), Step 2).
- **Interactive docs** — `/api/docs` (Swagger) and `/api/redoc`.
