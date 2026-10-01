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
- **SDO/AIA & HMI** — full-disk quick-looks; each channel takes the newest frame
  from SDO's dated browse archive (`assets/img/browse/YYYY/MM/DD/`), JSOC's HMI
  quick-looks (`jsoc1.stanford.edu/data/hmi/images/latest/`), or — last resort —
  SDO's `assets/img/latest/`, which froze on 2026-09-21 (HMI also left SDO's feeds
  on 2026-09-24). Timestamp from the frame filename / JSOC's `image_times_UTC`
  (see `backend/app/services/sdo_latest.py`).
- **GOES/SUVI** — `latest.png` that overwrites; timestamp taken from
  `Last-Modified` (see `backend/app/services/solar_image_service.py`).
- **SOHO/LASCO C2/C3** — coronagraph frames + short movies.
- **NASA DONKI (CCMC) — CME catalog + WSA-ENLIL arrivals** —
  `ccmc.gsfc.nasa.gov/DONKI-API/get/CME?startDate=&endDate=`, no API key; the
  last `CME_LOOKBACK_DAYS` (30) are re-fetched every `CME_POLL_SECONDS` (2 h)
  because analyses are revised for days, upserted by `activityID`. It replaced
  `kauai.ccmc.gsfc.nasa.gov/DONKI/WS/get/` on 2026-09-30 (same parameters and
  JSON); kauai and the `api.nasa.gov/DONKI` mirror now 301 to
  `ccmc.gsfc.nasa.gov/news/major-updates`, which the collector reports as "has
  moved" instead of following (see `backend/app/collectors/collect_donki.py`).
- **e-CALLISTO** — solar radio FITS archive + daily burst list; per-station frequency
  ranges differ; Sri Lanka (ACCIMT) is prioritised (see
  `backend/app/services/ecallisto_service.py`).

## Notes

- All display timestamps are converted to UTC; original timestamps are preserved.
- Provisional vs. final data must be marked, never silently mixed.
