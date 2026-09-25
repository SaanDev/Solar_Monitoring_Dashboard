"""SunPy-backed rendering for the Data Analysis feature.

Each function turns a ``sunpy.map.Map`` (or a sequence) into a styled PNG using a
WCS-aware (``projection=map``) matplotlib axis, matching the SunPy gallery look.
Single-image plot/crop renders synchronously and is cached by a hash of its
parameters (like the e-CALLISTO analyzer); heavier sequence work (difference,
movies) is layered on in later slices and reuses ``_render_map_to_png``.

SunPy/astropy are imported lazily inside the functions so the app starts even if
SunPy is missing — only the analysis endpoints then fail, not the whole API.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from app.services import aia_data_service as data  # noqa: E402

# Live preview renders crisp-but-fast; downloads render extra sharp; movie frames
# render a touch lower for speed and smaller files.
RENDER_DPI = 130
EXPORT_DPI = 200
MOVIE_DPI = 90

# Colormaps offered in the UI. "auto" uses the map's instrument default (e.g. the
# per-channel SDO/AIA colormaps SunPy registers on import).
COLORMAPS: list[str] = [
    "auto",
    "sdoaia94", "sdoaia131", "sdoaia171", "sdoaia193", "sdoaia211",
    "sdoaia304", "sdoaia335", "sdoaia1600", "sdoaia1700", "hmimag",
    # Multi-mission instrument colormaps (registered by sunpy on import; unknown
    # names degrade to the map's own default via resolve_cmap).
    "soholasco2", "soholasco3", "stereocor1", "stereocor2", "stereohi1", "stereohi2",
    "gray", "inferno", "magma", "viridis", "plasma", "hot",
    "RdBu_r", "seismic", "bwr",   # diverging — good for difference images
]
SCALES: list[str] = ["linear", "sqrt", "log", "asinh"]

# Coordinate graticule reference frames (ported solar_grid); "" = off.
GRID_FRAMES: list[str] = ["", "hgs", "hgc", "hci"]

# Dark theme matching the dashboard (see processing/plot_rendering.py).
_BG = "#0f1117"
_FG = "#94a3b8"
_TITLE = "#e2e8f0"
_GRID = "#334155"


@dataclass(frozen=True)
class PlotParams:
    cmap: str = "auto"
    scale: str = "linear"
    clip_low: float = 1.0          # percentile (used when vmin/vmax unset)
    clip_high: float = 99.9
    vmin: float | None = None
    vmax: float | None = None
    crop: bool = False
    bl_x: float = 0.0              # crop bottom-left, arcsec (helioprojective)
    bl_y: float = 0.0
    tr_x: float = 0.0             # crop top-right, arcsec
    tr_y: float = 0.0
    draw_limb: bool = False
    draw_grid: bool = False
    colorbar: bool = True
    # NRGF radial filter (coronagraphs): flattens the corona's radial fall-off so
    # faint CME fronts appear. Applied to the full frame before any crop.
    nrgf: bool = False
    # Coordinate graticule frame ("" = off, else hgs/hgc/hci — ported solar_grid).
    grid_frame: str = ""


# ── helpers ────────────────────────────────────────────────────────────────────


def resolve_cmap(name: str, m: Any) -> Any:
    """A matplotlib colormap by name, or the map's own default for ``auto``."""
    if not name or name == "auto":
        return m.plot_settings.get("cmap")
    try:
        return matplotlib.colormaps[name]
    except KeyError:
        return m.plot_settings.get("cmap")


def build_norm(m: Any, params: PlotParams) -> Any:
    """An ImageNormalize from explicit vmin/vmax or a percentile clip + stretch."""
    from astropy.visualization import (
        AsinhStretch,
        AsymmetricPercentileInterval,
        ImageNormalize,
        LinearStretch,
        LogStretch,
        ManualInterval,
        SqrtStretch,
    )

    stretch = {
        "linear": LinearStretch(),
        "sqrt": SqrtStretch(),
        "log": LogStretch(),
        "asinh": AsinhStretch(),
    }.get(params.scale, LinearStretch())

    if params.vmin is not None and params.vmax is not None:
        interval = ManualInterval(params.vmin, params.vmax)
    else:
        interval = AsymmetricPercentileInterval(params.clip_low, params.clip_high)
    return ImageNormalize(m.data, interval=interval, stretch=stretch, clip=False)


def submap(m: Any, params: PlotParams) -> Any:
    """Crop ``m`` to the requested arcsec rectangle (helioprojective)."""
    import astropy.units as u
    from astropy.coordinates import SkyCoord

    if params.tr_x <= params.bl_x or params.tr_y <= params.bl_y:
        raise ValueError("Crop top-right must be greater than bottom-left (arcsec).")
    bl = SkyCoord(params.bl_x * u.arcsec, params.bl_y * u.arcsec, frame=m.coordinate_frame)
    tr = SkyCoord(params.tr_x * u.arcsec, params.tr_y * u.arcsec, frame=m.coordinate_frame)
    return m.submap(bl, top_right=tr)


def _style_axes(ax: Any) -> None:
    """Apply the dark dashboard theme to a WCSAxes (best-effort)."""
    ax.set_facecolor(_BG)
    ax.set_xlabel("Helioprojective Longitude (Solar-X)", color=_FG, fontsize=9)
    ax.set_ylabel("Helioprojective Latitude (Solar-Y)", color=_FG, fontsize=9)
    try:
        for coord in ax.coords:
            coord.set_ticklabel(color=_FG, size=8)
            coord.set_axislabel_position("")
    except Exception:
        pass
    try:
        for spine in ax.spines.values():
            spine.set_edgecolor("#1e2535")
    except Exception:
        pass


def _render_map_to_png(
    m: Any,
    out: Path,
    *,
    cmap: Any,
    norm: Any,
    title: str,
    draw_limb: bool = False,
    draw_grid: bool = False,
    colorbar: bool = True,
    cbar_label: str = "",
    overlay: Any = None,
    tight: bool = True,
    dpi: int = RENDER_DPI,
) -> Path:
    """Render a single map to a styled PNG. Shared by every analysis view.

    ``overlay`` is an optional ``callable(ax)`` invoked after the base image is
    plotted (used to draw HMI contours, active-region boxes, markers, etc.).
    ``tight`` trims surrounding whitespace; movie frames set it False so every
    frame has identical pixel dimensions for the video encoder.
    """
    out.parent.mkdir(parents=True, exist_ok=True)
    fig = plt.figure(figsize=(7.6, 7.6), dpi=dpi)
    fig.patch.set_facecolor(_BG)
    ax = fig.add_subplot(projection=m)
    try:
        im = m.plot(axes=ax, cmap=cmap, norm=norm, title=False)
        if overlay is not None:
            overlay(ax)
        if draw_grid:
            try:
                m.draw_grid(axes=ax, color=_GRID, linewidth=0.4, alpha=0.6)
            except Exception:
                pass
        if draw_limb:
            try:
                m.draw_limb(axes=ax, color=_FG, linewidth=0.6)
            except Exception:
                pass
        _style_axes(ax)
        ax.set_title(title, color=_TITLE, fontsize=11, pad=8)
        if colorbar:
            cbar = fig.colorbar(im, ax=ax, pad=0.02, fraction=0.046)
            if cbar_label:
                cbar.set_label(cbar_label, color=_FG, fontsize=9)
            cbar.ax.tick_params(colors=_FG, labelsize=8)
            cbar.outline.set_edgecolor("#1e2535")
        fig.savefig(
            out, dpi=dpi,
            bbox_inches="tight" if tight else None,
            facecolor=fig.get_facecolor(),
        )
    finally:
        plt.close(fig)
    return out


def _title_for(m: Any) -> str:
    # Reuse the data service's safe extraction (AIA's m.measurement is a Quantity,
    # so plain str()/truthiness on it is unsafe).
    meta = data._map_metadata(m)
    when = meta["time"].strftime("%Y-%m-%d %H:%M:%S UTC") if meta["time"] else ""
    return f'{meta["instrument"]} {meta["measurement"]}  {when}'.strip()


def _cbar_label(m: Any) -> str:
    try:
        return f"Intensity [{m.unit}]" if m.unit is not None else "Intensity"
    except Exception:
        return "Intensity"


def _param_hash(*parts: Any) -> str:
    return hashlib.sha1(repr(parts).encode()).hexdigest()[:12]


def _apply_nrgf(m: Any) -> Any:
    """Apply the ported NRGF radial filter to a coronagraph map (full frame).

    Returns a new sunpy Map carrying the original WCS metadata, so crops,
    graticules and pixel↔world transforms keep working on the filtered image.
    """
    import sunpy.map

    from app.services.solar.coronagraph import nrgf, solar_center_from_meta

    center = solar_center_from_meta(m.meta, m.data.shape)
    import numpy as np

    filtered = nrgf(np.asarray(m.data, dtype=float), center)
    out = sunpy.map.Map(filtered, dict(m.meta))
    try:  # keep the instrument's plot defaults (colormap) on the derived map
        out.plot_settings = dict(m.plot_settings)
    except Exception:
        pass
    return out


def _graticule_overlay(m: Any, frame_key: str) -> Any:
    """Overlay callable drawing an HGS/HGC/HCI graticule (ported solar_grid).

    The graticule polylines come back in helioprojective arcsec; they are
    converted to pixel coordinates of ``m`` (crop-aware — a submap's WCS maps
    them correctly) and drawn with NaN gaps at the far hemisphere.
    """
    import astropy.units as u
    import numpy as np
    from astropy.coordinates import SkyCoord

    from app.services.solar.solar_grid import graticule_arcsec

    polylines, labels = graticule_arcsec(m, frame_key=frame_key.upper())

    def _overlay(ax: Any) -> None:
        for tx, ty in polylines:
            try:
                coords = SkyCoord(tx * u.arcsec, ty * u.arcsec, frame=m.coordinate_frame)
                px, py = m.wcs.world_to_pixel(coords)
            except Exception:
                continue
            ax.plot(np.asarray(px, float), np.asarray(py, float),
                    color=_GRID, linewidth=0.4, alpha=0.75)
        for text, lx, ly in labels:
            try:
                c = SkyCoord(lx * u.arcsec, ly * u.arcsec, frame=m.coordinate_frame)
                px, py = m.wcs.world_to_pixel(c)
                px, py = float(px), float(py)
            except Exception:
                continue
            if not (np.isfinite(px) and np.isfinite(py)):
                continue
            ny, nx = m.data.shape
            if not (0 <= px < nx and 0 <= py < ny):
                continue
            ax.text(px, py, text, color=_FG, fontsize=6, alpha=0.8)

    return _overlay if polylines else None


# ── single-image plot + crop (slice 1) ────────────────────────────────────────


def render_plot(
    session_id: str, frame: int, params: PlotParams, dpi: int = RENDER_DPI, tight: bool = True
) -> Path:
    """Render (or reuse a cached) plot PNG for one frame; returns the PNG path."""
    out = data.session_dir(session_id) / f"plot_{frame}_{_param_hash(params, dpi, tight)}.png"
    if out.exists():
        return out
    m = data.load_map(session_id, frame)
    if params.nrgf:
        m = _apply_nrgf(m)  # full frame first — the radial annuli need the whole image
    if params.crop:
        m = submap(m, params)
    cmap = resolve_cmap(params.cmap, m)
    norm = build_norm(m, params)
    overlay = _graticule_overlay(m, params.grid_frame) if params.grid_frame else None
    return _render_map_to_png(
        m,
        out,
        cmap=cmap,
        norm=norm,
        title=_title_for(m) + ("  · NRGF" if params.nrgf else ""),
        draw_limb=params.draw_limb,
        draw_grid=params.draw_grid,
        colorbar=params.colorbar,
        cbar_label="σ (NRGF)" if params.nrgf else _cbar_label(m),
        overlay=overlay,
        tight=tight,
        dpi=dpi,
    )


# ── exact-pixel "bare" render (interactive canvas background) ───────────────────


def render_bare(
    session_id: str,
    frame: int,
    params: PlotParams,
    mode: str = "plot",
    base_index: int = 0,
) -> Path:
    """Render one frame as a PNG whose pixels map 1:1 to the data array.

    No axes, colorbar, title or padding — ``matplotlib.image.imsave`` writes
    exactly ``(ny, nx)`` pixels with ``origin="lower"``, so the interactive
    canvas can convert clicks to data pixels linearly. ``mode`` mirrors the
    difference tool: "plot" (raw, optional NRGF), "running", "base".
    """
    import numpy as np
    from matplotlib.image import imsave

    out = data.session_dir(session_id) / (
        f"bare_{mode}_{frame}_{base_index}_{_param_hash(params)}.png"
    )
    if out.exists():
        return out

    m = data.load_map(session_id, frame)
    if mode in ("running", "base"):
        ref_index = frame - 1 if mode == "running" else base_index
        if ref_index < 0 or ref_index == frame:
            raise ValueError("Difference needs a distinct previous/base frame.")
        ref = data.load_map(session_id, ref_index)
        if m.data.shape != ref.data.shape:
            raise ValueError("Frames have different sizes; cannot difference them.")
        arr = np.asarray(m.data, float) - np.asarray(ref.data, float)
        if params.vmin is not None and params.vmax is not None:
            vmin, vmax = params.vmin, params.vmax
        else:
            lim = float(np.nanpercentile(np.abs(arr), params.clip_high)) or 1.0
            if not np.isfinite(lim) or lim == 0.0:
                lim = 1.0
            vmin, vmax = -lim, lim
        cmap_name = params.cmap if params.cmap not in ("", "auto") else "RdBu_r"
        cmap = resolve_cmap(cmap_name, m)
        normed = np.clip((arr - vmin) / (vmax - vmin), 0.0, 1.0)
    else:
        if params.nrgf:
            m = _apply_nrgf(m)
        arr = np.asarray(m.data, float)
        norm = build_norm(m, params)
        normed = np.asarray(norm(arr))
        normed = np.clip(np.nan_to_num(normed, nan=0.0), 0.0, 1.0)
        cmap = resolve_cmap(params.cmap, m)

    normed = np.nan_to_num(normed, nan=0.0)
    out.parent.mkdir(parents=True, exist_ok=True)
    imsave(str(out), normed, cmap=cmap, vmin=0.0, vmax=1.0, origin="lower", format="png")
    return out


def export_fits(session_id: str, frame: int, params: PlotParams) -> Path:
    """Write one frame (optionally cropped, WCS-correct via submap) as FITS."""
    out = data.session_dir(session_id) / f"export_{frame}_{_param_hash(params.crop, params.bl_x, params.bl_y, params.tr_x, params.tr_y)}.fits"
    if out.exists():
        return out
    m = data.load_map(session_id, frame)
    if params.crop:
        m = submap(m, params)
    m.save(str(out), overwrite=True)
    return out


# ── running / base difference (slice 3) ────────────────────────────────────────


def render_difference(
    session_id: str,
    index: int,
    diff_type: str,
    base_index: int,
    params: PlotParams,
    dpi: int = RENDER_DPI,
    tight: bool = True,
) -> Path:
    """Render a running- or base-difference frame.

    running: frame[index] − frame[index−1].  base: frame[index] − frame[base_index].
    Differences are signed, so a symmetric diverging colour scale is used (limits
    from the ±clip_high percentile of |Δ| unless vmin/vmax are given).
    """
    import numpy as np
    import sunpy.map
    from astropy.visualization import ImageNormalize, LinearStretch

    ref_index = index - 1 if diff_type == "running" else base_index
    if diff_type == "running" and ref_index < 0:
        raise ValueError("Running difference needs a previous frame (pick frame 2 or later).")
    if ref_index == index:
        raise ValueError("Difference reference frame must differ from the current frame.")

    out = data.session_dir(session_id) / (
        f"diff_{diff_type}_{index}_{ref_index}_{_param_hash(params, dpi, tight)}.png"
    )
    if out.exists():
        return out

    cur = data.load_map(session_id, index)
    ref = data.load_map(session_id, ref_index)
    if cur.data.shape != ref.data.shape:
        raise ValueError("Frames have different sizes; cannot difference them.")

    diff = np.asarray(cur.data, dtype=float) - np.asarray(ref.data, dtype=float)
    dmap = sunpy.map.Map(diff, cur.meta)
    if params.crop:
        dmap = submap(dmap, params)

    if params.vmin is not None and params.vmax is not None:
        vmin, vmax = params.vmin, params.vmax
    else:
        lim = float(np.nanpercentile(np.abs(dmap.data), params.clip_high))
        if not np.isfinite(lim) or lim == 0.0:
            lim = 1.0
        vmin, vmax = -lim, lim

    cmap_name = params.cmap if params.cmap not in ("", "auto") else "RdBu_r"
    norm = ImageNormalize(vmin=vmin, vmax=vmax, stretch=LinearStretch())
    title = f"{_title_for(cur)}  ({diff_type} difference)"
    return _render_map_to_png(
        dmap,
        out,
        cmap=resolve_cmap(cmap_name, dmap),
        norm=norm,
        title=title,
        draw_limb=params.draw_limb,
        draw_grid=params.draw_grid,
        colorbar=params.colorbar,
        cbar_label="Δ Intensity",
        tight=tight,
        dpi=dpi,
    )


# ── composite: AIA + HMI magnetogram contours (slice 4) ────────────────────────

# Reprojecting HMI onto the AIA WCS is the slow step, so cache it per (session, frame).
_HMI_REPROJ_CACHE: "dict[tuple[str, int], Any]" = {}


def _hmi_reprojected(session_id: str, frame: int, aia: Any, hmi_bytes: bytes | None) -> Any:
    key = (session_id, frame)
    cached = _HMI_REPROJ_CACHE.get(key)
    if cached is not None:
        return cached
    if hmi_bytes is None:
        raise ValueError(
            "No HMI magnetogram available for this frame's time — composites need "
            "a date with HMI synoptic coverage."
        )
    import sunpy.map

    tmp = data.session_dir(session_id) / "_hmi_tmp.fits"
    tmp.write_bytes(hmi_bytes)
    try:
        hmi = sunpy.map.Map(str(tmp))
        if isinstance(hmi, list):
            hmi = hmi[0]
        reproj = hmi.reproject_to(aia.wcs)
    finally:
        tmp.unlink(missing_ok=True)
    if len(_HMI_REPROJ_CACHE) > 8:
        _HMI_REPROJ_CACHE.clear()
    _HMI_REPROJ_CACHE[key] = reproj
    return reproj


def render_composite(
    session_id: str,
    frame: int,
    hmi_bytes: bytes | None,
    params: PlotParams,
    contour_level: float,
    dpi: int = RENDER_DPI,
) -> Path:
    """AIA base image overlaid with HMI line-of-sight magnetic-field contours
    (positive field red, negative cyan) at ±``contour_level`` Gauss."""
    out = data.session_dir(session_id) / (
        f"comp_{frame}_{int(contour_level)}_{_param_hash(params, dpi)}.png"
    )
    if out.exists():
        return out

    aia = data.load_map(session_id, frame)
    reproj = _hmi_reprojected(session_id, frame, aia, hmi_bytes)
    rdata = reproj.data
    level = abs(float(contour_level)) or 100.0

    def _overlay(ax: Any) -> None:
        ax.contour(rdata, levels=[level], colors="#ef4444", linewidths=0.7, alpha=0.9)
        ax.contour(rdata, levels=[-level], colors="#22d3ee", linewidths=0.7, alpha=0.9)

    cmap = resolve_cmap(params.cmap, aia)
    norm = build_norm(aia, params)
    title = f"{_title_for(aia)}  + HMI |B|={int(level)} G contours"
    return _render_map_to_png(
        aia, out, cmap=cmap, norm=norm, title=title,
        draw_limb=params.draw_limb, draw_grid=params.draw_grid,
        colorbar=params.colorbar, cbar_label=_cbar_label(aia),
        overlay=_overlay, dpi=dpi,
    )


# ── active-region identification (slice 4) ─────────────────────────────────────


def render_active_regions(
    session_id: str,
    frame: int,
    method: str,
    ar_list: list[dict[str, Any]],
    threshold_pct: float,
    params: PlotParams,
    dpi: int = RENDER_DPI,
) -> Path:
    """Identify active regions on an AIA/HMI frame.

    method "hek": mark NOAA SWPC active regions (from the HEK) with their numbers.
    method "threshold": box bright connected components above the ``threshold_pct``
    intensity percentile (scipy.ndimage labelling).
    """
    import numpy as np

    out = data.session_dir(session_id) / (
        f"ar_{method}_{frame}_{int(threshold_pct)}_{_param_hash(params, dpi)}.png"
    )
    if out.exists() and method == "threshold":  # HEK list may change; don't cache it
        return out

    m = data.load_map(session_id, frame)

    def _overlay(ax: Any) -> None:
        import matplotlib.patches as mpatches

        if method == "threshold":
            import scipy.ndimage as ndi

            d = np.asarray(m.data, dtype=float)
            finite = d[np.isfinite(d)]
            if finite.size == 0:
                return
            thr = np.nanpercentile(finite, threshold_pct)
            mask = np.nan_to_num(d, nan=-np.inf) > thr
            labeled, n = ndi.label(mask)
            if n == 0:
                return
            min_area = max(40, int(0.0004 * d.size))
            count = 0
            for sl in ndi.find_objects(labeled):
                if sl is None:
                    continue
                ys, xs = sl
                h = ys.stop - ys.start
                w = xs.stop - xs.start
                if h * w < min_area:
                    continue
                count += 1
                ax.add_patch(
                    mpatches.Rectangle(
                        (xs.start, ys.start), w, h, fill=False,
                        edgecolor="#a3e635", linewidth=0.8,
                    )
                )
            ax.set_xlabel(
                f"Helioprojective Longitude (Solar-X) — {count} bright regions",
                color=_FG, fontsize=9,
            )
        else:  # HEK NOAA markers
            import astropy.units as u
            from astropy.coordinates import SkyCoord

            ny, nx = m.data.shape
            for ar in ar_list:
                coord = SkyCoord(
                    ar["x"] * u.arcsec, ar["y"] * u.arcsec,
                    frame=m.coordinate_frame,
                )
                try:
                    px, py = m.world_to_pixel(coord)
                    px = float(px.value)
                    py = float(py.value)
                except Exception:
                    continue
                if not (0 <= px < nx and 0 <= py < ny):
                    continue
                ax.plot(px, py, marker="o", markersize=5, markerfacecolor="none",
                        markeredgecolor="#22d3ee", markeredgewidth=1.0)
                if ar.get("ar"):
                    ax.text(px + 12, py + 12, str(ar["ar"]), color="#22d3ee",
                            fontsize=8, fontweight="bold")

    title = (
        f"{_title_for(m)}  · NOAA active regions"
        if method == "hek"
        else f"{_title_for(m)}  · bright-region detection"
    )
    cmap = resolve_cmap(params.cmap, m)
    norm = build_norm(m, params)
    return _render_map_to_png(
        m, out, cmap=cmap, norm=norm, title=title,
        draw_limb=params.draw_limb, draw_grid=params.draw_grid,
        colorbar=params.colorbar, cbar_label=_cbar_label(m),
        overlay=_overlay, dpi=dpi,
    )


# ── movies / time-lapse (slice 5) ──────────────────────────────────────────────


def make_movie(
    session_id: str,
    fmt: str = "mp4",
    fps: int = 8,
    mode: str = "plot",
    params: PlotParams | None = None,
    *,
    progress: Any = None,
) -> tuple[str, dict]:
    """Assemble a time-lapse from a multi-frame session (job function).

    mode "plot": each frame as a plain image. mode "difference": running difference.
    A single intensity scale is fixed across all frames (so the movie doesn't
    flicker), and every frame is rendered at the same pixel size (tight=False) for
    the encoder. Returns ``(path, meta)``; MP4 via ffmpeg, GIF via Pillow.
    """
    import numpy as np
    import imageio.v2 as imageio
    from astropy.visualization import AsymmetricPercentileInterval

    p = params or PlotParams()
    fps = max(1, min(int(fps), 30))
    session = data.get_session(session_id)
    n = session.n_frames
    if n < 2:
        raise ValueError("A movie needs a multi-frame session.")

    # Fix the colour scale across frames for a stable (non-flickering) movie.
    if p.vmin is None or p.vmax is None:
        if mode == "difference":
            cur = data.load_map(session_id, 1)
            ref = data.load_map(session_id, 0)
            d = np.asarray(cur.data, float) - np.asarray(ref.data, float)
            lim = float(np.nanpercentile(np.abs(d), p.clip_high)) or 1.0
            fixed = replace(p, vmin=-lim, vmax=lim)
        else:
            mid = data.load_map(session_id, n // 2)
            lo, hi = AsymmetricPercentileInterval(p.clip_low, p.clip_high).get_limits(mid.data)
            fixed = replace(p, vmin=float(lo), vmax=float(hi))
    else:
        fixed = p

    indices = list(range(1, n)) if mode == "difference" else list(range(n))
    if progress:
        progress(0.05, f"Rendering {len(indices)} frames…")
    frame_pngs: list[Path] = []
    for k, i in enumerate(indices):
        if mode == "difference":
            fp = render_difference(session_id, i, "running", 0, fixed, dpi=MOVIE_DPI, tight=False)
        else:
            fp = render_plot(session_id, i, fixed, dpi=MOVIE_DPI, tight=False)
        frame_pngs.append(fp)
        if progress:
            progress(0.1 + 0.7 * (k + 1) / len(indices), f"Rendered {k + 1}/{len(indices)} frames")

    ext = "mp4" if fmt == "mp4" else "gif"
    out = data.session_dir(session_id) / f"movie_{mode}_{fps}fps.{ext}"
    if progress:
        progress(0.85, f"Encoding {ext.upper()}…")
    if ext == "mp4":
        writer = imageio.get_writer(
            str(out), fps=fps, codec="libx264", quality=8,
            macro_block_size=16, output_params=["-pix_fmt", "yuv420p"],
        )
    else:
        writer = imageio.get_writer(str(out), mode="I", duration=1.0 / fps, loop=0)
    try:
        for fp in frame_pngs:
            writer.append_data(imageio.imread(fp))
    finally:
        writer.close()

    if progress:
        progress(1.0, "Done")
    return str(out), {"kind": "artifact", "format": ext, "frames": len(frame_pngs), "fps": fps}
