# Agent Rules

## General

- Work in small steps.
- Do not rewrite unrelated files.
- Keep changes focused on the requested task.
- Add or update tests when behavior changes.
- Prefer simple, readable code over clever code.
- Use UTC for all timestamps.
- Do not hard-code local machine paths.
- Read `.env.example` before adding new environment variables.
- Keep large data files out of Git (FITS, PNGs, images, movies).

## Backend

- Use FastAPI.
- Keep routes thin — no business logic in route handlers.
- Put data collection logic in `collectors/`.
- Put domain logic in `services/`.
- Put reusable processing functions in `processing/`.
- Use Pydantic schemas for request and response models.
- Handle missing data gracefully with structured error responses.
- Add tests for new routes and processing functions.
- Use dependency injection for DB sessions and settings.

## Frontend

- Use TypeScript — no `any` types.
- Use reusable components.
- Keep all API calls in `lib/api.ts`.
- Keep shared types in `lib/types.ts`.
- Use loading, error, and empty states for every data panel.
- Make plots readable in dark mode.
- Show UTC labels in all plots and timestamps.

## Space-weather data

- Preserve original timestamps.
- Convert all display timestamps to UTC.
- Store source name and update time with each data product.
- Show data-source health in the UI.
- Mark provisional data clearly when applicable.
- Do not silently mix real-time, provisional, and final values.

## e-CALLISTO

- Do not assume all stations have the same frequency range.
- Do not assume all FITS files have identical headers.
- Keep raw FITS files unchanged.
- Save processed products separately.
- Store processing method and parameters with every generated spectrum.
- Use downsampled images for dashboard display.
- Keep scientific analysis reproducible.
