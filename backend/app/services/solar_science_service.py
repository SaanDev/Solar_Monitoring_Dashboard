"""Specialized science for the Data Analysis feature (ported desktop modules).

* **J-maps** (``solar.hi_jmap``) — time–elongation maps for STEREO/HI (and
  coronagraph running-diff variants): background-subtract the frame stack,
  sample a radial slit at a position angle per frame, stack profiles over time.
* **HMI vector field** (``solar.hmi_vector_field``) — fetch hmi.B_720s segments
  via JSOC, resolve the 180° azimuth disambiguation, and draw quiver arrows /
  streamlines / |B| tint over the session's HMI frame.
* **Compare viewpoint** (``solar.multiview``) — reproject another session's map
  onto the current frame's WCS/observer for a two-viewpoint blink.

Heavy steps (J-map build, vector-segment download) run as ``job_manager`` jobs;
parameter-driven renders are synchronous and disk-cached like the other views.
"""
from __future__ import annotations

import hashlib
import logging
import threading
from pathlib import Path
from typing import Any, Callable

from app.config import settings
from app.services import aia_data_service as data
from app.services import aia_analysis_service as analysis

logger = logging.getLogger(__name__)


def _hash(*parts: Any) -> str:
    return hashlib.sha1(repr(parts).encode()).hexdigest()[:12]


# ── J-map (time–elongation) ──────────────────────────────────────────────────────


def jmap_job(
    session_id: str,
    pa_deg: float,
    background: str = "median",
    half_width: int = 2,
    *,
    progress: Callable[[float, str], None] | None = None,
) -> tuple[str, dict]:
    """Build and render a J-map from every frame of a session (job function)."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.dates as mdates
    import matplotlib.pyplot as plt
    import numpy as np

    from app.services.solar.coronagraph import solar_center_from_meta
    from app.services.solar.hi_jmap import build_jmap, pixel_to_elongation_deg, subtract_background

    def _p(frac: float, msg: str = "") -> None:
        if progress:
            progress(frac, msg)

    session = data.get_session(session_id)
    if session.n_frames < 3:
        raise ValueError("A J-map needs at least 3 frames (more gives a clearer track).")

    _p(0.05, f"Loading {session.n_frames} frames…")
    maps = [data.load_map(session_id, fr.index) for fr in session.frames]
    arrays = [np.asarray(m.data, dtype=float) for m in maps]
    times = [fr.time for fr in session.frames]

    _p(0.35, f"Subtracting {background} background…")
    subtracted = subtract_background(arrays, method=background)

    center = solar_center_from_meta(maps[0].meta, arrays[0].shape)
    _p(0.55, f"Sampling slit at PA {pa_deg:.0f}°…")
    jm = build_jmap(subtracted, center, _pa_to_math_angle(pa_deg), half_width=int(half_width))

    # Elongation axis in degrees from the plate scale.
    try:
        import astropy.units as u

        cdelt = float(maps[0].scale.axis1.to_value(u.arcsec / u.pix))
    except Exception:
        cdelt = 1.0
    elong = pixel_to_elongation_deg(jm.radii_pixels, cdelt)

    _p(0.8, "Rendering…")
    out = data.session_dir(session_id) / f"jmap_{_hash(pa_deg, background, half_width, session.n_frames)}.png"

    img = jm.image.T  # (elongation, time) for time-on-x display
    lim = np.nanpercentile(np.abs(img), 99.0) or 1.0
    have_times = all(t is not None for t in times)
    fig = plt.figure(figsize=(9.0, 5.4), dpi=140)
    fig.patch.set_facecolor(analysis._BG)
    ax = fig.add_subplot()
    if have_times:
        x0, x1 = mdates.date2num(times[0]), mdates.date2num(times[-1])
    else:
        x0, x1 = 0, len(times) - 1
    im = ax.imshow(
        img,
        origin="lower",
        aspect="auto",
        cmap="gray",
        vmin=-lim,
        vmax=lim,
        extent=[x0, x1, float(elong[0]), float(elong[-1])],
    )
    if have_times:
        ax.xaxis_date()
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
    ax.set_xlabel("Time (UTC)" if have_times else "Frame", color=analysis._FG, fontsize=9)
    ax.set_ylabel("Elongation (deg)", color=analysis._FG, fontsize=9)
    ax.set_title(
        f"J-map · {session.instrument} {session.detector} · PA {pa_deg:.0f}° · {background} background",
        color=analysis._TITLE,
        fontsize=11,
    )
    ax.tick_params(colors=analysis._FG, labelsize=8)
    ax.set_facecolor(analysis._BG)
    for spine in ax.spines.values():
        spine.set_edgecolor("#1e2535")
    cbar = fig.colorbar(im, ax=ax, pad=0.02, fraction=0.046)
    cbar.set_label("ΔI", color=analysis._FG, fontsize=9)
    cbar.ax.tick_params(colors=analysis._FG, labelsize=8)
    cbar.outline.set_edgecolor("#1e2535")
    fig.savefig(out, dpi=140, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close(fig)

    _p(1.0, "Done")
    return str(out), {
        "kind": "artifact",
        "format": "png",
        "frames": session.n_frames,
        "pa_deg": pa_deg,
        "background": background,
    }


def _pa_to_math_angle(pa_deg: float) -> float:
    """Solar position angle (N→E, from +Y) → slit math angle (CCW from +X).

    The ported slit sampler measures angles counter-clockwise from the +x axis
    in display orientation (90° = up); solar PA is from north through east
    (counter-clockwise on the sky with west right), so math = PA + 90°.
    """
    return (float(pa_deg) + 90.0) % 360.0


# ── HMI vector field ─────────────────────────────────────────────────────────────

# Assembled vector frames per session (bx/by/bz grids are a few MB each).
_VECTOR_FRAMES: dict[str, list[Any]] = {}
_VECTOR_LOCK = threading.Lock()


def _vector_dir(session_id: str) -> Path:
    d = data.session_dir(session_id) / "_vector"
    d.mkdir(parents=True, exist_ok=True)
    return d


def vector_prepare_job(
    session_id: str,
    frame: int = 0,
    *,
    progress: Callable[[float, str], None] | None = None,
) -> tuple[str, dict]:
    """Fetch + assemble hmi.B_720s vector segments near a frame's time (job).

    Segments land in ``<session>/_vector`` (reused on re-prepare); the assembled
    ``HmiVectorFrame``s are cached in memory for the render endpoint.
    """
    from datetime import timedelta

    from app.services.solar.hmi_vector_field import load_vector_frames
    from app.services.solar.jsoc_client import export_hmi_vector_urls

    def _p(frac: float, msg: str = "") -> None:
        if progress:
            progress(frac, msg)

    when = data.frame_time(session_id, frame)
    if when is None:
        raise ValueError("This frame has no timestamp; the vector field needs a dated frame.")
    when = when.replace(tzinfo=None) if when.tzinfo else when

    vdir = _vector_dir(session_id)
    existing = sorted(vdir.glob("*.fits"))
    if not existing:
        if not settings.jsoc_email:
            raise ValueError(
                "Fetching hmi.B_720s vector segments needs a JSOC-registered notify "
                "e-mail — set JSOC_EMAIL in the backend environment "
                "(register at http://jsoc.stanford.edu/ajax/register_email.html)."
            )
        _p(0.05, "Requesting hmi.B_720s staged export via JSOC (can take a minute)…")
        # Staged fits protocol: as-is SUMS segments carry no header keywords,
        # which the vector axis transforms need for exact arcsec mapping.
        export = export_hmi_vector_urls(
            start=when - timedelta(minutes=12),
            end=when + timedelta(minutes=12),
            email=settings.jsoc_email,
            method="url",
            protocol="fits",
        )
        from app.services.solar_acquisition_service import _download_url

        n = len(export.urls)
        for k, entry in enumerate(export.urls):
            name = entry.filename or f"vector_{k:02d}.fits"
            name = name.replace("/", "_").replace("\\", "_")
            dest = vdir / f"{k:02d}_{name}"
            if not dest.exists():
                _download_url(entry.url, dest)
            _p(0.1 + 0.6 * (k + 1) / n, f"Downloaded segment {k + 1}/{n}")
        existing = sorted(vdir.glob("*.fits"))

    _p(0.75, "Assembling vector components (disambiguation + Bx/By/Bz)…")
    frames = load_vector_frames([str(p) for p in existing])
    with _VECTOR_LOCK:
        _VECTOR_FRAMES[session_id] = frames

    _p(1.0, "Done")
    return str(vdir), {
        "kind": "artifact",
        "format": "vector-cache",
        "time_steps": len(frames),
        "segments": len(existing),
    }


def _get_vector_frame(session_id: str, frame: int) -> Any:
    from app.services.solar.hmi_vector_field import load_vector_frames, nearest_vector_frame

    with _VECTOR_LOCK:
        frames = _VECTOR_FRAMES.get(session_id)
    if not frames:
        vdir = _vector_dir(session_id)
        paths = sorted(vdir.glob("*.fits"))
        if not paths:
            raise ValueError("Vector segments not prepared yet — run Prepare first.")
        frames = load_vector_frames([str(p) for p in paths])
        with _VECTOR_LOCK:
            _VECTOR_FRAMES[session_id] = frames
    when = data.frame_time(session_id, frame)
    when = when.replace(tzinfo=None) if (when and when.tzinfo) else when
    vf = nearest_vector_frame(frames, when)
    if vf is None:
        vf = frames[0]
    return vf


def render_vector_field(
    session_id: str,
    frame: int,
    params: Any,
    show_arrows: bool = True,
    show_streamlines: bool = False,
    show_magnitude: bool = False,
    grid_step_px: int = 64,
    min_gauss: float = 200.0,
    dpi: int | None = None,
) -> Path:
    """Render the session's HMI frame with the vector-field overlay.

    Arrows are polarity-coloured (red = +Bz toward the observer, blue = −Bz);
    geometry arrives in arcsec from ``build_overlay_geometry`` and is drawn via
    the frame's WCS so it lands exactly on the displayed magnetogram.
    """
    import astropy.units as u
    import numpy as np
    from astropy.coordinates import SkyCoord

    from app.services.solar.hmi_vector_field import VectorOverlayOptions, build_overlay_geometry

    dpi = dpi or analysis.RENDER_DPI
    out = data.session_dir(session_id) / (
        f"vector_{frame}_{_hash(params, show_arrows, show_streamlines, show_magnitude, grid_step_px, min_gauss, dpi)}.png"
    )
    if out.exists():
        return out

    m = data.load_map(session_id, frame)
    vf = _get_vector_frame(session_id, frame)
    options = VectorOverlayOptions(
        show_arrows=show_arrows,
        show_streamlines=show_streamlines,
        show_magnitude=show_magnitude,
        grid_step_px=int(grid_step_px),
        min_transverse_gauss=float(min_gauss),
    )
    geometry = build_overlay_geometry(vf, options)

    def _to_px(xs: np.ndarray, ys: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        finite = np.isfinite(xs) & np.isfinite(ys)
        px = np.full(xs.shape, np.nan)
        py = np.full(ys.shape, np.nan)
        if finite.any():
            coords = SkyCoord(xs[finite] * u.arcsec, ys[finite] * u.arcsec, frame=m.coordinate_frame)
            wx, wy = m.wcs.world_to_pixel(coords)
            px[finite] = wx
            py[finite] = wy
        return px, py

    def _overlay(ax: Any) -> None:
        if geometry.magnitude_rgba is not None and geometry.magnitude_rect is not None:
            x0, x1, y0, y1 = geometry.magnitude_rect
            corners = SkyCoord([x0, x1] * u.arcsec, [y0, y1] * u.arcsec, frame=m.coordinate_frame)
            (px0, px1), (py0, py1) = m.wcs.world_to_pixel(corners)
            ax.imshow(
                geometry.magnitude_rgba,
                origin="lower",
                extent=[float(px0), float(px1), float(py0), float(py1)],
                zorder=2,
            )
        if geometry.streamline_count:
            sx, sy = _to_px(geometry.stream_x, geometry.stream_y)
            ax.plot(sx, sy, color="#e2e8f0", linewidth=0.5, alpha=0.7, zorder=3)
        if geometry.arrow_count:
            for xs, ys, color in (
                (geometry.arrows_pos_x, geometry.arrows_pos_y, "#ef4444"),
                (geometry.arrows_neg_x, geometry.arrows_neg_y, "#3b82f6"),
            ):
                if xs.size:
                    px, py = _to_px(xs, ys)
                    ax.plot(px, py, color=color, linewidth=0.7, alpha=0.9, zorder=4)

    cmap = analysis.resolve_cmap(params.cmap, m)
    norm = analysis.build_norm(m, params)
    n_steps = f"B⊥≥{int(min_gauss)} G · step {int(grid_step_px)} px"
    return analysis._render_map_to_png(
        m,
        out,
        cmap=cmap,
        norm=norm,
        title=f"{analysis._title_for(m)}  · vector field ({n_steps})",
        draw_limb=params.draw_limb,
        colorbar=params.colorbar,
        cbar_label=analysis._cbar_label(m),
        overlay=_overlay,
        dpi=dpi,
    )


# ── compare viewpoint (multi-view reprojection) ──────────────────────────────────

_REPROJ_CACHE: dict[tuple[str, int, str, int], Any] = {}
_REPROJ_LOCK = threading.Lock()


def compare_info(session_id: str, frame: int, other_id: str, other_frame: int) -> dict:
    """Observer separation + labels for a two-viewpoint pair."""
    from app.services.solar.multiview import observer_separation_deg

    a = data.load_map(session_id, frame)
    b = data.load_map(other_id, other_frame)
    try:
        sep = observer_separation_deg(a, b)
    except Exception:
        sep = None
    ma = data._map_metadata(a)
    mb = data._map_metadata(b)
    return {
        "separation_deg": sep,
        "primary": f'{ma["instrument"]} {ma["measurement"]}'.strip(),
        "secondary": f'{mb["instrument"]} {mb["measurement"]}'.strip(),
        "primary_time": ma["time"].isoformat() if ma["time"] else None,
        "secondary_time": mb["time"].isoformat() if mb["time"] else None,
    }


def _reprojected(session_id: str, frame: int, other_id: str, other_frame: int) -> Any:
    from app.services.solar.multiview import reproject_map_to

    key = (session_id, frame, other_id, other_frame)
    with _REPROJ_LOCK:
        hit = _REPROJ_CACHE.get(key)
    if hit is not None:
        return hit
    a = data.load_map(session_id, frame)
    b = data.load_map(other_id, other_frame)
    reproj = reproject_map_to(b, a)
    with _REPROJ_LOCK:
        if len(_REPROJ_CACHE) > 6:
            _REPROJ_CACHE.clear()
        _REPROJ_CACHE[key] = reproj
    return reproj


def render_compare(
    session_id: str,
    frame: int,
    other_id: str,
    other_frame: int,
    view: str,
    params: Any,
    dpi: int | None = None,
) -> Path:
    """Render one side of a two-viewpoint blink.

    ``view="primary"`` is the session frame; ``view="reprojected"`` is the other
    session's frame reprojected onto the primary WCS/observer (same pixel grid,
    so the frontend can blink the two URLs directly).
    """
    dpi = dpi or analysis.RENDER_DPI
    out = data.session_dir(session_id) / (
        f"compare_{view}_{frame}_{other_id[:8]}_{other_frame}_{_hash(params, dpi)}.png"
    )
    if out.exists():
        return out

    if view == "primary":
        m = data.load_map(session_id, frame)
        title = f"{analysis._title_for(m)}  · primary view"
    else:
        m = _reprojected(session_id, frame, other_id, other_frame)
        other = data.get_session(other_id)
        title = f"{other.instrument} {other.measurement} → reprojected to primary view"

    cmap = analysis.resolve_cmap(params.cmap, m)
    norm = analysis.build_norm(m, params)
    return analysis._render_map_to_png(
        m,
        out,
        cmap=cmap,
        norm=norm,
        title=title,
        draw_limb=params.draw_limb,
        colorbar=params.colorbar,
        cbar_label=analysis._cbar_label(m),
        dpi=dpi,
    )
