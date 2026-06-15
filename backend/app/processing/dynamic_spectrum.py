"""Full pipeline: load → clean → render → return metadata."""
from datetime import datetime, timezone, timedelta
from pathlib import Path
import uuid
import numpy as np

from app.processing.fits_loader import load_ecallisto_fits, FitsData
from app.processing.background_subtraction import background_subtract_db
from app.processing.plot_rendering import render_spectrum_png
from app.config import settings


def parse_obs_start(header: dict) -> datetime | None:
    """Parse the observation start time.

    e-CALLISTO uses DATE-OBS='YYYY/MM/DD' and TIME-OBS='HH:MM:SS.sss' (UTC),
    but some files use an ISO DATE-OBS. Handle both.
    """
    date_obs = header.get("DATE-OBS") or header.get("DATE_OBS")
    time_obs = header.get("TIME-OBS") or header.get("TIME_OBS")
    if not date_obs:
        return None

    date_str = str(date_obs).strip()
    # ISO form (date already contains 'T' / time component)
    if "T" in date_str:
        try:
            return datetime.fromisoformat(date_str.replace("Z", "+00:00")).replace(
                tzinfo=timezone.utc
            )
        except ValueError:
            return None

    date_str = date_str.replace("/", "-")
    time_str = str(time_obs).strip() if time_obs else "00:00:00"
    for fmt in ("%H:%M:%S.%f", "%H:%M:%S", "%H:%M"):
        try:
            t = datetime.strptime(time_str, fmt).time()
            d = datetime.strptime(date_str, "%Y-%m-%d").date()
            return datetime.combine(d, t, tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def process_fits(
    fits_path: Path, station: str = "", out_filename: str | None = None
) -> dict:
    """Process a FITS file into a dynamic-spectrum PNG.

    If out_filename is given and already exists, rendering is skipped (cache).
    """
    out_filename = out_filename or f"{station or 'unknown'}_{uuid.uuid4().hex[:8]}.png"
    out_path = Path(settings.spectra_dir) / out_filename

    fd: FitsData = load_ecallisto_fits(fits_path)
    obs_start = parse_obs_start(fd.header)
    duration_s = float(fd.time_axis[-1] - fd.time_axis[0]) if len(fd.time_axis) > 1 else 0.0

    if not out_path.exists():
        # e-CALLISTO background subtraction: dB above per-channel background.
        db = background_subtract_db(fd.data)
        render_spectrum_png(
            data=db,
            time_axis=fd.time_axis,
            freq_axis=fd.freq_axis,
            out_path=out_path,
            station=station,
            obs_start=obs_start,
        )

    end_time = (
        obs_start + timedelta(seconds=duration_s) if obs_start and duration_s else None
    )

    return {
        "station": station,
        "start_time": obs_start,
        "end_time": end_time,
        "freq_min_mhz": float(fd.freq_axis.min()),
        "freq_max_mhz": float(fd.freq_axis.max()),
        "duration_s": duration_s,
        "image_path": str(out_path),
        "image_filename": out_filename,
        "processing_method": "digit2voltage_dB - per-channel median (dB above background)",
    }
