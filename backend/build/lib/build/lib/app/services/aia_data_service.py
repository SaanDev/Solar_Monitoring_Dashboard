"""Session storage + data acquisition for the Data Analysis feature.

A session is a directory ``settings.analysis_dir/<id>/`` holding one or more solar
FITS frames plus a ``meta.json`` describing them. Frames come from three sources:

* **upload**  — the user posts AIA/HMI FITS files they already have.
* **fetch**   — SunPy ``Fido`` downloads full-resolution AIA frames by date/time.
* **archive** — reuse the existing 1024px JSOC synoptic FITS pipeline
  (``solar_archive_service``) already wired into the dashboard's Archive page.

Loaded ``sunpy.map.Map`` objects are cached (small LRU) so interactive re-renders
of one frame don't re-read the FITS each time. SunPy is imported lazily so the app
still starts (and the rest of the API still serves) if SunPy is unavailable.
"""
from __future__ import annotations

import json
import logging
import re
import threading
from collections import OrderedDict
from datetime import date as date_cls, datetime, timezone
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4

from app.config import settings
from app.schemas.data_analysis_schema import AnalysisSession, FrameMeta, WavelengthOption

logger = logging.getLogger(__name__)

_ID_RE = re.compile(r"^[0-9a-f]{32}$")

# AIA EUV/UV channels offered for fetch + listed in the options endpoint.
AIA_WAVELENGTHS: list[str] = ["94", "131", "171", "193", "211", "304", "335", "1600", "1700"]


def wavelength_options() -> list[WavelengthOption]:
    return [WavelengthOption(code=w, label=f"AIA {w} Å") for w in AIA_WAVELENGTHS]


# ── id / paths ────────────────────────────────────────────────────────────────


def _safe_id(id: str) -> str:
    if not _ID_RE.match(id or ""):
        raise ValueError("Invalid analysis session id")
    return id


def session_dir(id: str) -> Path:
    """Path to a session directory (path-traversal safe)."""
    _safe_id(id)
    base = Path(settings.analysis_dir).resolve()
    p = (base / id).resolve()
    if base not in p.parents:
        raise ValueError("Invalid analysis session id")
    return p


def _meta_path(id: str) -> Path:
    return session_dir(id) / "meta.json"


def frame_path(id: str, index: int) -> Path:
    """Absolute path of a session's frame FITS by index."""
    session = get_session(id)
    for fr in session.frames:
        if fr.index == index:
            return session_dir(id) / fr.filename
    raise FileNotFoundError(f"Frame {index} not found in session {id}")


# ── metadata extraction ───────────────────────────────────────────────────────


def _map_metadata(m: Any) -> dict[str, Any]:
    """Pull the display fields we care about off a sunpy Map (all best-effort)."""
    import astropy.units as u

    wl: float | None = None
    try:
        wl = float(m.wavelength.to_value(u.angstrom))
    except Exception:
        wl = None

    detector = str(getattr(m, "detector", "") or "")
    if wl is not None:
        # Uniform label for any wavelength-selected imager (AIA/EUVI/SUVI/…).
        # Header-derived strings can carry mojibake (e.g. synoptic AIA "Ã…").
        measurement = f"{int(round(wl))} Å"
    else:
        measurement = str(getattr(m, "measurement", "") or "")

    when: datetime | None = None
    try:
        when = m.date.to_datetime().replace(tzinfo=timezone.utc)
    except Exception:
        when = None

    exptime: float | None = None
    try:
        raw_exp = m.meta.get("exptime", m.meta.get("xposure"))
        if raw_exp is not None:
            exptime = float(raw_exp)
    except Exception:
        exptime = None

    return {
        "observatory": str(getattr(m, "observatory", "") or ""),
        "instrument": str(getattr(m, "instrument", "") or ""),
        "detector": detector,
        "measurement": measurement,
        "wavelength_angstrom": wl,
        "time": when,
        "exptime": exptime,
        "width": int(m.dimensions[0].value),
        "height": int(m.dimensions[1].value),
    }


# ── session build / persistence ───────────────────────────────────────────────


def _write_meta(session: AnalysisSession) -> None:
    _meta_path(session.id).write_text(session.model_dump_json(indent=2), encoding="utf-8")


def get_session(id: str) -> AnalysisSession:
    path = _meta_path(id)
    if not path.exists():
        raise FileNotFoundError(f"Analysis session not found: {id}")
    return AnalysisSession.model_validate_json(path.read_text(encoding="utf-8"))


def _north_up(m: Any) -> Any:
    """Rotate a map to solar-north-up when its CCD orientation is rolled.

    HMI and JSOC lev1 AIA arrive with CROTA2 ≈ 180° (south up) and LASCO
    carries a few degrees of roll; ``Map.rotate()`` re-grids to north-up and
    updates the WCS consistently, so renders, the interactive canvas and all
    measurements stay exact. Already-north-up maps pass through untouched.
    """
    try:
        import numpy as np

        matrix = np.asarray(m.rotation_matrix, dtype=float)
        # Identity to within ~2.5 deg → leave the pixels alone.
        if abs(matrix[0, 0] - 1.0) < 1e-3 and abs(matrix[0, 1]) < 0.04:
            return m
        return m.rotate(missing=np.nan)
    except Exception:
        return m


def _smart_map(path: str | Path) -> Any:
    """Load one FITS into a sunpy Map, repairing LASCO/SUVI headers if needed.

    Plain ``sunpy.map.Map`` fails on SOHO/LASCO frames missing ``CUNIT`` and on
    GOES/SUVI L1b frames with a malformed ``CONTINUE`` card; the ported ingest
    loaders backfill/repair those. Uploads and AIA/HMI/STEREO frames take the
    ordinary path. All maps are normalised to solar-north-up.
    """
    import sunpy.map

    try:
        m = sunpy.map.Map(str(path))
        return _north_up(m[0] if isinstance(m, list) else m)
    except Exception:
        pass
    # Header-repair fallbacks (each raises if the file isn't its instrument).
    from app.services.solar.lasco_ingest import load_lasco_map
    from app.services.solar.suvi_ingest import load_suvi_map

    last_exc: Exception | None = None
    for loader in (load_lasco_map, load_suvi_map):
        try:
            m = loader(str(path))
            return _north_up(m[0] if isinstance(m, list) else m)
        except Exception as exc:  # noqa: BLE001 - try the next repair loader
            last_exc = exc
    raise last_exc or ValueError(f"Could not read {path} as a solar map")


def build_session(id: str, source: str, files: list[Path]) -> AnalysisSession:
    """Load each FITS as a Map, order by observation time, persist session meta.

    Frames are renamed to ``frame_000.fits`` … in time order inside the session
    directory so downstream code can address them by index.
    """
    from app.services.solar.instrument_profiles import classify_frame

    if not files:
        raise ValueError("No FITS files for session")

    loaded: list[tuple[Path, dict[str, Any]]] = []
    for f in files:
        m = _smart_map(f)
        meta = _map_metadata(m)
        try:
            meta["science_class"] = classify_frame(m)
        except Exception:
            meta["science_class"] = "disk_euv"
        loaded.append((f, meta))

    # Order by observation time (files without a time keep input order at the end).
    loaded.sort(key=lambda lm: (lm[1]["time"] is None, lm[1]["time"] or datetime.min))

    sdir = session_dir(id)
    frames: list[FrameMeta] = []
    for i, (src_path, meta) in enumerate(loaded):
        dest = sdir / f"frame_{i:03d}.fits"
        if src_path.resolve() != dest.resolve():
            dest.write_bytes(src_path.read_bytes())
        frames.append(
            FrameMeta(
                index=i,
                time=meta["time"],
                filename=dest.name,
                detector=meta["detector"],
                exptime=meta.get("exptime"),
            )
        )

    first = loaded[0][1]
    session = AnalysisSession(
        id=id,
        source=source,
        observatory=first["observatory"],
        instrument=first["instrument"],
        detector=first["detector"],
        measurement=first["measurement"],
        wavelength_angstrom=first["wavelength_angstrom"],
        reference_time=frames[0].time,
        width=first["width"],
        height=first["height"],
        science_class=first.get("science_class", "disk_euv"),
        n_frames=len(frames),
        frames=frames,
    )
    _write_meta(session)
    _MAP_CACHE.invalidate(id)
    return session


# ── fetch via SunPy Fido (VSO) ─────────────────────────────────────────────────


def _prep_aia(path: Path) -> None:
    """Calibrate an AIA frame to level 1.5 in place (aiapy: pointing + register).

    Downloads the pointing table from JSOC on first use, so this is slow and
    network-bound — gated behind the ``prep`` flag in the UI.
    """
    import aiapy.calibrate as cal
    import sunpy.map

    m = sunpy.map.Map(str(path))
    m = cal.update_pointing(m)
    m = cal.register(m)
    m.save(str(path), overwrite=True)


def fetch_via_fido(
    wavelength: str,
    when: datetime,
    prep: bool = False,
    *,
    progress: Callable[[float, str], None] | None = None,
) -> tuple[str, dict]:
    """Download the AIA frame nearest ``when`` for ``wavelength`` into a new session.

    Returns ``(session_dir, meta)`` where meta carries the built session — the job
    manager stores it so ``/jobs/{id}`` can hand the session back to the client.
    """
    import astropy.units as u
    from datetime import timedelta
    from sunpy.net import Fido, attrs as a

    def _p(frac: float, msg: str = "") -> None:
        if progress:
            progress(frac, msg)

    _p(0.05, f"Searching VSO for AIA {wavelength} A...")
    # astropy Time accepts naive datetimes (treated as UTC); a tz-aware ISO string
    # with a +00:00 offset is rejected, so normalise to naive UTC first.
    when_utc = when.astimezone(timezone.utc).replace(tzinfo=None) if when.tzinfo else when
    window = timedelta(seconds=30)
    query = Fido.search(
        a.Time(when_utc - window, when_utc + window),
        a.Instrument.aia,
        a.Wavelength(float(wavelength) * u.angstrom),
    )
    if query.file_num == 0:
        raise ValueError(f"No AIA {wavelength} Å data found near {when:%Y-%m-%d %H:%M} UTC")

    id = uuid4().hex
    sdir = session_dir(id)
    sdir.mkdir(parents=True, exist_ok=True)
    try:
        _p(0.25, "Downloading FITS (full-resolution AIA can take a few minutes)...")
        results = Fido.fetch(query[0, 0], path=str(sdir / "{file}"), progress=False)
        # The JSOC export mirror often stalls while staging the file and only
        # serves it on a later request, so retry a couple of times before giving up.
        attempts = 1
        while results.errors and attempts < 3:
            attempts += 1
            _p(min(0.55, 0.25 + 0.1 * attempts), f"Mirror busy; retry {attempts - 1}...")
            results = Fido.fetch(results, progress=False)
        if results.errors or not results:
            detail = str(results.errors[0]) if results.errors else "no file returned"
            raise ValueError(
                "Full-resolution download from VSO/JSOC failed "
                f"({detail}). The export mirror may be busy — try again, or use "
                "the Archive source for the 1024px synoptic frame."
            )
        downloaded = [Path(f) for f in results]
        if prep:
            _p(0.6, "Calibrating to level 1.5 (aiapy)…")
            for f in downloaded:
                _prep_aia(f)
        _p(0.85, "Building session…")
        session = build_session(id, "fetch", downloaded)
        for f in downloaded:  # build_session copied to frame_NNN.fits; drop originals
            f.unlink(missing_ok=True)
    except Exception:
        _rmtree(sdir)
        raise
    _p(1.0, "Done")
    return str(sdir), {"kind": "session", "session": session.model_dump(mode="json")}


# ── archive source (reuse the existing JSOC synoptic pipeline) ──────────────────


def _archive_key(wavelength: str) -> str:
    """Map an AIA channel code to a solar_archive_service catalog id (e.g. aia171)."""
    return f"aia{wavelength.zfill(3)}"


def fetch_archive_sequence(
    date_str: str,
    start_hm: str,
    step_min: int,
    n_frames: int,
    wavelength: str,
    *,
    progress: Callable[[float, str], None] | None = None,
) -> tuple[str, dict]:
    """Build a multi-frame session from the JSOC synoptic archive (job function).

    Pulls the synoptic frame nearest each time t0, t0+step, … via the existing
    ``fetch_fts`` pipeline. Reliable and fast (~1 s/frame); feeds difference images
    and movies. Duplicate frames (same underlying file) are skipped.
    """
    import asyncio
    from datetime import datetime as _dt, timedelta

    from app.services.solar_archive_service import fetch_fts

    n_frames = max(2, min(int(n_frames), 60))
    d = _dt.strptime(date_str, "%Y-%m-%d").date()
    base = _dt.combine(d, _dt.strptime(start_hm, "%H:%M").time())
    targets = [base + timedelta(minutes=int(step_min) * i) for i in range(n_frames)]
    key = _archive_key(wavelength)

    id = uuid4().hex
    sdir = session_dir(id)
    sdir.mkdir(parents=True, exist_ok=True)

    async def _grab() -> list[Path]:
        files: list[Path] = []
        seen: set[str] = set()
        for i, t in enumerate(targets):
            try:
                res = await fetch_fts(d, t.strftime("%H:%M"), key)
            except Exception:  # noqa: BLE001 - missing frame is non-fatal
                res = None
            if res is not None:
                content, fname = res
                if fname not in seen:
                    seen.add(fname)
                    p = sdir / f"_seq_{i:03d}.fits"
                    p.write_bytes(content)
                    files.append(p)
            if progress:
                progress(0.1 + 0.7 * (i + 1) / n_frames, f"Fetched {i + 1}/{n_frames} frames")
        return files

    try:
        files = asyncio.run(_grab())
        if len(files) < 2:
            raise ValueError(
                "Fewer than 2 distinct frames found for that range — widen the time "
                "window or pick a date with synoptic coverage."
            )
        if progress:
            progress(0.85, "Building session…")
        session = build_session(id, "archive", files)
        for f in files:
            f.unlink(missing_ok=True)
    except Exception:
        _rmtree(sdir)
        raise
    if progress:
        progress(1.0, "Done")
    return str(sdir), {"kind": "session", "session": session.model_dump(mode="json")}


async def store_from_archive(date: date_cls, time_hm: str, wavelength: str) -> AnalysisSession | None:
    """Pull the 1024px synoptic AIA FITS nearest the time from the JSOC archive."""
    from app.services.solar_archive_service import fetch_fts

    # fetch_fts raises (e.g. 404) when the synoptic directory for that date/hour
    # doesn't exist yet — treat any failure as "not available" so the route can
    # return a clean 404 instead of a 500.
    try:
        result = await fetch_fts(date, time_hm, _archive_key(wavelength))
    except Exception as exc:  # noqa: BLE001 - network/HTTP errors mean "no data"
        logger.info("archive fetch failed for %s %s %s: %s", date, time_hm, wavelength, exc)
        result = None
    if result is None:
        return None
    content, _fname = result
    id = uuid4().hex
    sdir = session_dir(id)
    sdir.mkdir(parents=True, exist_ok=True)
    tmp = sdir / "_archive.fits"
    try:
        tmp.write_bytes(content)
        session = build_session(id, "archive", [tmp])
    except Exception:
        _rmtree(sdir)
        raise
    finally:
        tmp.unlink(missing_ok=True)
    return session


# ── interactive canvas: WCS metadata + exact coordinate readout ─────────────────


def frame_wcs_meta(session_id: str, frame: int) -> dict[str, Any]:
    """WCS/geometry needed by the interactive canvas for pixel↔arcsec mapping.

    ``center_x``/``center_y`` is the Sun-centre pixel (0-based), so the client's
    linear mapping ``Tx ≈ cdelt1·(PC(px−c))`` is exact up to TAN distortion
    (negligible at disk scales). The server-side ``/coord`` endpoint does the
    exact transform for click readouts.
    """
    import astropy.units as u
    import numpy as np
    from astropy.coordinates import SkyCoord

    m = load_map(session_id, frame)
    ny, nx = m.data.shape

    try:
        cpx = m.wcs.world_to_pixel(SkyCoord(0 * u.arcsec, 0 * u.arcsec, frame=m.coordinate_frame))
        center = (float(cpx[0]), float(cpx[1]))
        if not (np.isfinite(center[0]) and np.isfinite(center[1])):
            raise ValueError
    except Exception:
        center = ((nx - 1) / 2.0, (ny - 1) / 2.0)

    try:
        cdelt1 = float(m.scale.axis1.to_value(u.arcsec / u.pix))
        cdelt2 = float(m.scale.axis2.to_value(u.arcsec / u.pix))
    except Exception:
        cdelt1 = cdelt2 = 1.0
    try:
        pc = [[float(v) for v in row] for row in np.asarray(m.rotation_matrix)]
    except Exception:
        pc = [[1.0, 0.0], [0.0, 1.0]]
    try:
        rsun = float(m.rsun_obs.to_value(u.arcsec))
    except Exception:
        rsun = 960.0

    meta = _map_metadata(m)
    return {
        "nx": nx,
        "ny": ny,
        "center_x": center[0],
        "center_y": center[1],
        "cdelt1": cdelt1,
        "cdelt2": cdelt2,
        "pc": pc,
        "rsun_arcsec": rsun,
        "time": meta["time"].isoformat() if meta["time"] else None,
        "instrument": meta["instrument"],
        "detector": meta["detector"],
        "measurement": meta["measurement"],
        "exptime": meta.get("exptime"),
    }


def coord_readout(
    session_id: str, frame: int, px: float, py: float, frame_key: str = "HGS"
) -> dict[str, Any]:
    """Exact WCS readout for a data pixel: arcsec, R☉, position angle, lon/lat.

    Position angle follows the solar convention (from north through east).
    Off-disk sight lines have no lon/lat (``None``).
    """
    import astropy.units as u
    import math

    import numpy as np

    from app.services.solar.solar_grid import point_lonlat

    m = load_map(session_id, frame)
    ny, nx = m.data.shape
    coord = m.wcs.pixel_to_world(float(px), float(py))
    tx = float(coord.Tx.to_value(u.arcsec))
    ty = float(coord.Ty.to_value(u.arcsec))
    try:
        rsun = float(m.rsun_obs.to_value(u.arcsec))
    except Exception:
        rsun = 960.0
    r_arcsec = math.hypot(tx, ty)
    pa = math.degrees(math.atan2(-tx, ty)) % 360.0  # N→E convention

    lonlat = point_lonlat(tx, ty, m, frame_key=frame_key)

    value: float | None = None
    ix, iy = int(round(px)), int(round(py))
    if 0 <= ix < nx and 0 <= iy < ny:
        raw = float(np.asarray(m.data, dtype=float)[iy, ix])
        value = raw if np.isfinite(raw) else None

    return {
        "px": float(px),
        "py": float(py),
        "tx_arcsec": tx,
        "ty_arcsec": ty,
        "r_rsun": r_arcsec / rsun if rsun > 0 else None,
        "position_angle_deg": pa,
        "lon_deg": lonlat[0] if lonlat else None,
        "lat_deg": lonlat[1] if lonlat else None,
        "frame_key": frame_key.upper(),
        "value": value,
    }


# ── composite / active-region helpers (slice 4) ─────────────────────────────────


def frame_time(session_id: str, frame: int) -> datetime | None:
    session = get_session(session_id)
    for fr in session.frames:
        if fr.index == frame:
            return fr.time
    raise FileNotFoundError(f"Frame {frame} not found in session {session_id}")


_HMI_BYTES_CACHE: "OrderedDict[tuple[str, str], bytes]" = OrderedDict()
_HMI_CACHE_MAX = 8


async def fetch_hmi_bytes(date: date_cls, time_hm: str) -> bytes | None:
    """HMI line-of-sight magnetogram (M_720s) FITS nearest a time, from the JSOC
    synoptic archive. Cached so repeated composite renders don't re-download."""
    from app.services.solar_archive_service import fetch_fts

    key = (date.isoformat(), time_hm)
    hit = _HMI_BYTES_CACHE.get(key)
    if hit is not None:
        _HMI_BYTES_CACHE.move_to_end(key)
        return hit
    try:
        result = await fetch_fts(date, time_hm, "hmib")
    except Exception as exc:  # noqa: BLE001 - missing/again is non-fatal
        logger.info("HMI fetch failed for %s %s: %s", date, time_hm, exc)
        return None
    if result is None:
        return None
    content, _ = result
    _HMI_BYTES_CACHE[key] = content
    _HMI_BYTES_CACHE.move_to_end(key)
    while len(_HMI_BYTES_CACHE) > _HMI_CACHE_MAX:
        _HMI_BYTES_CACHE.popitem(last=False)
    return content


def _hek_query(date: date_cls, time_hm: str) -> list[dict[str, Any]]:
    """NOAA SWPC active regions near a time from the HEK (blocking; run in a thread)."""
    from datetime import datetime as _dt, timedelta

    from sunpy.net import Fido, attrs as a

    t = _dt.combine(date, _dt.strptime(time_hm, "%H:%M").time())
    res = Fido.search(
        a.Time(t - timedelta(hours=12), t + timedelta(hours=12)),
        a.hek.AR,
        a.hek.FRM.Name == "NOAA SWPC Observer",
    )
    try:
        table = res["hek"]
    except Exception:
        return []
    ars: list[dict[str, Any]] = []
    seen: set = set()
    for row in table:
        try:
            x = float(row["hpc_x"])
            y = float(row["hpc_y"])
        except (KeyError, TypeError, ValueError):
            continue
        num = row.get("ar_noaanum") if hasattr(row, "get") else row["ar_noaanum"]
        key = num or (round(x), round(y))
        if key in seen:
            continue
        seen.add(key)
        ars.append({"ar": int(num) if num else 0, "x": x, "y": y})
    return ars


async def fetch_hek_active_regions(date: date_cls, time_hm: str) -> list[dict[str, Any]]:
    """NOAA active regions near a time (HEK), resolved off the event loop."""
    import asyncio

    try:
        return await asyncio.to_thread(_hek_query, date, time_hm)
    except Exception as exc:  # noqa: BLE001 - HEK outage is non-fatal
        logger.info("HEK query failed for %s %s: %s", date, time_hm, exc)
        return []


def store_upload(files: list[tuple[bytes, str]]) -> AnalysisSession:
    """Persist uploaded FITS bytes (one or more frames) into a new session."""
    id = uuid4().hex
    sdir = session_dir(id)
    sdir.mkdir(parents=True, exist_ok=True)
    tmp_paths: list[Path] = []
    try:
        for i, (content, filename) in enumerate(files):
            ext = ".fits.gz" if filename.lower().endswith(".gz") else ".fits"
            tmp = sdir / f"_upload_{i:03d}{ext}"
            tmp.write_bytes(content)
            tmp_paths.append(tmp)
        session = build_session(id, "upload", tmp_paths)
    except Exception:
        _rmtree(sdir)
        raise
    finally:
        for tmp in tmp_paths:
            tmp.unlink(missing_ok=True)
    return session


# ── session bundles (.ecsolar) + regions CSV (ported solar_session) ─────────────


def export_session_bundle(
    session_id: str,
    picks: list[dict[str, Any]] | None = None,
    display: dict[str, Any] | None = None,
) -> Path:
    """Bundle a session into a desktop-compatible ``.ecsolar`` ZIP.

    Embeds the raw FITS frames plus ``meta.json`` (source description, display
    state, and CME height–time picks in the desktop's serialized format, so the
    file opens in the e-CALLISTO FITS Analyzer too).
    """
    import astropy.units as u
    import math

    from app.services.solar.solar_session import serialize_picks, write_solar_session

    session = get_session(session_id)
    sdir = session_dir(session_id)
    frame_paths = [str(sdir / fr.filename) for fr in session.frames]

    # Web picks {frame, px, py} → desktop {frame: (when, h_rsun, x_arc, y_arc, pa)}.
    desktop_picks: dict[int, tuple] = {}
    for p in picks or []:
        try:
            frame = int(p["frame"])
            m = load_map(session_id, frame)
            coord = m.wcs.pixel_to_world(float(p["px"]), float(p["py"]))
            x_arc = float(coord.Tx.to_value(u.arcsec))
            y_arc = float(coord.Ty.to_value(u.arcsec))
            try:
                rsun = float(m.rsun_obs.to_value(u.arcsec))
            except Exception:
                rsun = 960.0
            h_rsun = math.hypot(x_arc, y_arc) / rsun
            pa = math.degrees(math.atan2(-x_arc, y_arc)) % 360.0
            desktop_picks[frame] = (frame_time(session_id, frame), h_rsun, x_arc, y_arc, pa)
        except Exception:  # noqa: BLE001 - drop unconvertible picks, keep the rest
            continue

    meta: dict[str, Any] = {
        "source": {
            "kind": session.source,
            "observatory": session.observatory,
            "instrument": session.instrument,
            "detector": session.detector,
            "measurement": session.measurement,
            "science_class": session.science_class,
        },
        "display": dict(display or {}),
        "picks": serialize_picks(desktop_picks),
        "app": "Solar Monitoring Dashboard",
    }
    out = sdir / f"session_{session_id[:8]}.ecsolar"
    write_solar_session(str(out), meta=meta, frame_paths=frame_paths)
    return out


def import_session_bundle(content: bytes) -> dict[str, Any]:
    """Restore a ``.ecsolar`` bundle into a new session.

    Returns ``{"session": AnalysisSession, "picks": [...], "display": {...}}`` —
    picks are converted back to web canvas coordinates (frame, px, py) via each
    frame's WCS, so desktop-made picks land on the right pixels here too.
    """
    import astropy.units as u
    from astropy.coordinates import SkyCoord

    from app.services.solar.solar_session import deserialize_picks, read_solar_session

    id = uuid4().hex
    sdir = session_dir(id)
    sdir.mkdir(parents=True, exist_ok=True)
    bundle = sdir / "_import.ecsolar"
    extract = sdir / "_extract"
    try:
        bundle.write_bytes(content)
        result = read_solar_session(str(bundle), extract_dir=str(extract))
        session = build_session(id, "upload", [Path(p) for p in result.frame_paths])
    except Exception:
        _rmtree(extract)
        _rmtree(sdir)
        raise
    finally:
        bundle.unlink(missing_ok=True)
        _rmtree(extract)

    web_picks: list[dict[str, Any]] = []
    for frame, (_when, _h, x_arc, y_arc, _pa) in deserialize_picks(result.meta.get("picks")).items():
        try:
            m = load_map(id, frame)
            coord = SkyCoord(x_arc * u.arcsec, y_arc * u.arcsec, frame=m.coordinate_frame)
            px, py = m.wcs.world_to_pixel(coord)
            web_picks.append({"frame": frame, "px": float(px), "py": float(py)})
        except Exception:  # noqa: BLE001 - skip picks that fall off the new grid
            continue

    return {
        "session": session,
        "picks": web_picks,
        "display": result.meta.get("display") or {},
    }


def regions_csv(
    session_id: str, frame: int, threshold_pct: float = 98.0, min_area_px: int = 40
) -> Path:
    """Detect bright regions (ported detect_active_regions) and write a CSV."""
    import csv

    import astropy.units as u
    import numpy as np

    from app.services.solar.solar_data_analysis import detect_active_regions

    m = load_map(session_id, frame)
    regions = detect_active_regions(
        np.asarray(m.data, dtype=float),
        threshold_percentile=float(threshold_pct),
        min_area_px=int(min_area_px),
    )
    out = session_dir(session_id) / f"regions_{frame}_{int(threshold_pct)}.csv"
    with out.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(
            ["id", "centroid_x_px", "centroid_y_px", "centroid_tx_arcsec", "centroid_ty_arcsec",
             "bbox_x0", "bbox_x1", "bbox_y0", "bbox_y1", "area_px", "peak", "mean"]
        )
        for r in regions:
            # Exact arcsec centroid via the map WCS (detection ran without a transform).
            coord = m.wcs.pixel_to_world(r.centroid_x, r.centroid_y)
            tx = float(coord.Tx.to_value(u.arcsec))
            ty = float(coord.Ty.to_value(u.arcsec))
            w.writerow(
                [r.region_id, f"{r.centroid_x:.2f}", f"{r.centroid_y:.2f}", f"{tx:.1f}", f"{ty:.1f}",
                 *r.bbox, r.area_px, f"{r.peak:.2f}", f"{r.mean:.2f}"]
            )
    return out


def _rmtree(path: Path) -> None:
    try:
        for child in path.glob("*"):
            child.unlink(missing_ok=True)
        path.rmdir()
    except Exception:
        pass


# ── loaded-Map LRU cache ───────────────────────────────────────────────────────


class _MapCache:
    """Small LRU of loaded sunpy Maps so interactive re-renders stay snappy."""

    def __init__(self, maxsize: int = 8) -> None:
        self._store: "OrderedDict[tuple[str, int], Any]" = OrderedDict()
        self._lock = threading.Lock()
        self._max = maxsize

    def get(self, id: str, index: int, loader: Callable[[], Any]) -> Any:
        key = (id, index)
        with self._lock:
            hit = self._store.get(key)
            if hit is not None:
                self._store.move_to_end(key)
                return hit
        m = loader()  # load outside the lock (slow I/O)
        with self._lock:
            self._store[key] = m
            self._store.move_to_end(key)
            while len(self._store) > self._max:
                self._store.popitem(last=False)
        return m

    def invalidate(self, id: str) -> None:
        with self._lock:
            for key in [k for k in self._store if k[0] == id]:
                self._store.pop(key, None)


_MAP_CACHE = _MapCache()


def load_map(id: str, index: int = 0) -> Any:
    """Return a cached ``sunpy.map.Map`` for one frame of a session."""
    path = frame_path(id, index)

    def _loader() -> Any:
        # _smart_map repairs LASCO/SUVI headers; AIA/HMI/STEREO load plainly.
        return _smart_map(path)

    return _MAP_CACHE.get(id, index, _loader)
