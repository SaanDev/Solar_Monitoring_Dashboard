# Data Sources

External data feeds the dashboard ingests, with their URLs, cadence, formats, and
quirks.

> **Status: stub — to be written.**

## Intended sections

For each source: feed URL, cadence, format, timezone handling, and known gotchas.

- **NOAA SWPC — GOES X-ray flux** — `services.swpc.noaa.gov/json/goes/primary/`,
  1-minute, rolling 6h/1d/3d/7d windows (see `backend/app/collectors/collect_goes_xrs.py`).
- **NOAA SWPC — GOES proton flux** — multi-channel integral flux.
- **NOAA SWPC — Planetary K-index** — `products/noaa-planetary-k-index.json`,
  3-hourly (see `backend/app/collectors/collect_kp.py`).
- **Dst index** — provisional vs. final values; source + cadence.
- **SDO/AIA & HMI, GOES/SUVI** — full-disk browse images via `latest` URLs that
  overwrite; timestamp taken from `Last-Modified` (see
  `backend/app/services/solar_image_service.py`).
- **SOHO/LASCO C2/C3** — coronagraph frames + short movies.
- **e-CALLISTO** — solar radio FITS archive + daily burst list; per-station frequency
  ranges differ; Sri Lanka (ACCIMT) is prioritised (see
  `backend/app/services/ecallisto_service.py`).

## Notes

- All display timestamps are converted to UTC; original timestamps are preserved.
- Provisional vs. final data must be marked, never silently mixed.
