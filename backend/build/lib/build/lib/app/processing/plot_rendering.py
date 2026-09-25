"""Render dynamic spectrum PNG using matplotlib."""
from datetime import datetime, timedelta
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
from matplotlib.ticker import FuncFormatter


def render_spectrum_png(
    data: np.ndarray,
    time_axis: np.ndarray,
    freq_axis: np.ndarray,
    out_path: Path,
    station: str = "",
    obs_start: datetime | None = None,
    vmin: float = -1.0,
    vmax: float = 8.0,
    cmap="magma",
    cbar_label: str = "dB above background",
    time_unit: str = "seconds",
    dpi: int = 200,
) -> Path:
    """Save a background-subtracted dynamic spectrum as PNG. Returns the path.

    `data` is expected to already be background-subtracted (dB above background);
    vmin/vmax default to the e-CALLISTO display range. `cmap` accepts a matplotlib
    colormap name or Colormap object. `time_unit` is "seconds" (from start) or
    "utc" (wall-clock ticks, requires `obs_start`). `dpi` controls render sharpness.
    """
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # Higher-resolution figure so the spectrogram is crisp in the panel and exports.
    fig, ax = plt.subplots(figsize=(10, 6.5), dpi=dpi)
    fig.patch.set_facecolor("#0f1117")
    ax.set_facecolor("#0f1117")

    t_min, t_max = time_axis[0], time_axis[-1]
    f_min, f_max = freq_axis[-1], freq_axis[0]  # high freq at top

    im = ax.imshow(
        data,
        aspect="auto",
        origin="upper",
        extent=[t_min, t_max, f_min, f_max],
        cmap=cmap,
        norm=mcolors.Normalize(vmin=vmin, vmax=vmax),
        interpolation="nearest",
    )

    if time_unit == "utc" and obs_start is not None:
        def _fmt(x, _pos):
            return (obs_start + timedelta(seconds=float(x))).strftime("%H:%M:%S")
        ax.xaxis.set_major_formatter(FuncFormatter(_fmt))
        ax.set_xlabel("Time (UTC)", color="#94a3b8", fontsize=10)
    else:
        ax.set_xlabel("Time (s from start)", color="#94a3b8", fontsize=10)
    ax.set_ylabel("Frequency (MHz)", color="#94a3b8", fontsize=10)
    ax.tick_params(colors="#94a3b8", labelsize=9)
    for spine in ax.spines.values():
        spine.set_edgecolor("#1e2535")

    cbar = fig.colorbar(im, ax=ax, pad=0.01, fraction=0.04)
    cbar.set_label(cbar_label, color="#94a3b8", fontsize=9)
    cbar.ax.tick_params(colors="#94a3b8", labelsize=8)
    cbar.outline.set_edgecolor("#1e2535")

    title = station
    if obs_start:
        title += f"  {obs_start.strftime('%Y-%m-%d %H:%M UTC')}"
    ax.set_title(title, color="#e2e8f0", fontsize=11, pad=6)

    plt.tight_layout(pad=0.6)
    fig.savefig(out_path, dpi=dpi, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close(fig)
    return out_path


# ── Shock-analysis renderers ─────────────────────────────────────────────────
#
# The burst-isolation lasso is drawn in the browser over the spectrogram image, so the
# frontend must map screen pixels → data coordinates. render_spectrum_png uses
# bbox_inches="tight", which crops margins after layout and makes the plotted-area pixel
# box non-deterministic. The shock spectrogram below instead uses a FIXED axes rectangle
# and saves the full canvas (no tight bbox), so the axes box in PNG pixels is exactly
# (fraction * figure size) — returned as `geometry` for the overlay to map against.

_SHOCK_FIG_W_IN = 10.0
_SHOCK_FIG_H_IN = 6.5
# Axes rectangle in figure fraction [left, bottom, width, height] (origin bottom-left).
_SHOCK_AXES = (0.09, 0.11, 0.88, 0.82)
_BG = "#0f1117"
_GRID = "#1e2535"
_MUTED = "#94a3b8"
_FG = "#e2e8f0"


def shock_geometry(time_axis: np.ndarray, freq_axis: np.ndarray, dpi: int = 150) -> dict:
    """Plotted-area geometry for the shock spectrogram — deterministic from the fixed
    axes rectangle + data extents, so it can be computed without rendering the PNG."""
    img_w = _SHOCK_FIG_W_IN * dpi
    img_h = _SHOCK_FIG_H_IN * dpi
    left, bottom, width, height = _SHOCK_AXES
    x0 = left * img_w
    x1 = (left + width) * img_w
    # Figure fraction origin is bottom-left; PNG pixel origin is top-left.
    y0 = (1.0 - (bottom + height)) * img_h
    y1 = (1.0 - bottom) * img_h
    return {
        "img_w": float(img_w),
        "img_h": float(img_h),
        "axes_px": [float(x0), float(y0), float(x1), float(y1)],
        "t0": float(time_axis[0]),
        "t1": float(time_axis[-1]),
        "freq_top": float(freq_axis[0]),
        "freq_bottom": float(freq_axis[-1]),
    }


def render_shock_spectrogram(
    data: np.ndarray,
    time_axis: np.ndarray,
    freq_axis: np.ndarray,
    out_path: Path,
    station: str = "",
    obs_start: datetime | None = None,
    vmin: float = -1.0,
    vmax: float = 8.0,
    cmap="magma",
    time_unit: str = "seconds",
    dpi: int = 150,
) -> tuple[Path, dict]:
    """Render the spectrogram with a fixed axes rectangle for lasso overlay mapping.

    Returns ``(path, geometry)`` where ``geometry`` gives the plotted-area box in PNG
    pixels (top-left origin) plus the data extents, so the browser can convert lasso
    pixels to ``[time_seconds, freq_mhz]`` coordinates.
    """
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig = plt.figure(figsize=(_SHOCK_FIG_W_IN, _SHOCK_FIG_H_IN), dpi=dpi)
    fig.patch.set_facecolor(_BG)
    ax = fig.add_axes(_SHOCK_AXES)
    ax.set_facecolor(_BG)

    t_min, t_max = float(time_axis[0]), float(time_axis[-1])
    # extent uses [t_min, t_max, f_bottom, f_top]; e-CALLISTO stores high freq first.
    f_top, f_bottom = float(freq_axis[0]), float(freq_axis[-1])
    ax.imshow(
        data,
        aspect="auto",
        origin="upper",
        extent=[t_min, t_max, f_bottom, f_top],
        cmap=cmap,
        norm=mcolors.Normalize(vmin=vmin, vmax=vmax),
        interpolation="nearest",
    )

    if time_unit == "utc" and obs_start is not None:
        def _fmt(x, _pos):
            return (obs_start + timedelta(seconds=float(x))).strftime("%H:%M:%S")
        ax.xaxis.set_major_formatter(FuncFormatter(_fmt))
        ax.set_xlabel("Time (UTC)", color=_MUTED, fontsize=10)
    else:
        ax.set_xlabel("Time (s from start)", color=_MUTED, fontsize=10)
    ax.set_ylabel("Frequency (MHz)", color=_MUTED, fontsize=10)
    ax.tick_params(colors=_MUTED, labelsize=9)
    for spine in ax.spines.values():
        spine.set_edgecolor(_GRID)

    title = station
    if obs_start:
        title += f"  {obs_start.strftime('%Y-%m-%d %H:%M UTC')}"
    if title:
        ax.set_title(title, color=_FG, fontsize=11, pad=6)

    fig.savefig(out_path, dpi=dpi, facecolor=fig.get_facecolor())
    plt.close(fig)
    return out_path, shock_geometry(time_axis, freq_axis, dpi)


def render_fit_plot(
    out_path: Path,
    points_time: np.ndarray,
    points_freq: np.ndarray,
    fit_time: np.ndarray | None = None,
    fit_freq: np.ndarray | None = None,
    title: str = "",
    equation: str = "",
    dpi: int = 150,
) -> Path:
    """Scatter of maximum-intensity points with the power-law best-fit overlay."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(8, 5), dpi=dpi)
    fig.patch.set_facecolor(_BG)
    ax.set_facecolor(_BG)

    ax.scatter(points_time, points_freq, s=12, color="#38bdf8", label="Max intensity", zorder=3)
    if fit_time is not None and fit_freq is not None and len(fit_time):
        label = equation or "Best fit"
        ax.plot(fit_time, fit_freq, color="#f87171", lw=2, label=label, zorder=4)

    ax.set_xlabel("Time (s)", color=_MUTED, fontsize=10)
    ax.set_ylabel("Frequency (MHz)", color=_MUTED, fontsize=10)
    if title:
        ax.set_title(title, color=_FG, fontsize=11, pad=6)
    ax.tick_params(colors=_MUTED, labelsize=9)
    ax.grid(True, color=_GRID, alpha=0.5)
    for spine in ax.spines.values():
        spine.set_edgecolor(_GRID)
    leg = ax.legend(facecolor=_BG, edgecolor=_GRID, labelcolor=_FG, fontsize=9)
    if leg:
        leg.get_frame().set_alpha(0.8)

    fig.tight_layout(pad=0.6)
    fig.savefig(out_path, dpi=dpi, facecolor=fig.get_facecolor())
    plt.close(fig)
    return out_path


_EXTRA_PLOT_SPECS = {
    "speed_height": ("shock_height_rs", "shock_speed_km_s", "Shock Height (Rₛ)", "Shock Speed (km/s)", "Shock Speed vs Height"),
    "speed_freq": ("shock_freq_mhz", "shock_speed_km_s", "Frequency (MHz)", "Shock Speed (km/s)", "Shock Speed vs Frequency"),
    "height_freq": ("shock_freq_mhz", "shock_height_rs", "Frequency (MHz)", "Shock Height (Rₛ)", "Shock Height vs Frequency"),
}


def render_extra_plot(out_path: Path, kind: str, curves: dict, dpi: int = 150) -> Path:
    """Render a derived shock plot (speed-vs-height / speed-vs-freq / height-vs-freq)."""
    if kind not in _EXTRA_PLOT_SPECS:
        raise ValueError(f"Unknown extra plot kind: {kind}")
    xkey, ykey, xlabel, ylabel, title = _EXTRA_PLOT_SPECS[kind]
    x = np.asarray(curves.get(xkey) or [], dtype=float)
    y = np.asarray(curves.get(ykey) or [], dtype=float)
    order = np.argsort(x)
    x, y = x[order], y[order]

    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(8, 5), dpi=dpi)
    fig.patch.set_facecolor(_BG)
    ax.set_facecolor(_BG)
    ax.plot(x, y, color="#34d399", lw=2, marker="o", ms=3)
    ax.set_xlabel(xlabel, color=_MUTED, fontsize=10)
    ax.set_ylabel(ylabel, color=_MUTED, fontsize=10)
    ax.set_title(title, color=_FG, fontsize=11, pad=6)
    ax.tick_params(colors=_MUTED, labelsize=9)
    ax.grid(True, color=_GRID, alpha=0.5)
    for spine in ax.spines.values():
        spine.set_edgecolor(_GRID)

    fig.tight_layout(pad=0.6)
    fig.savefig(out_path, dpi=dpi, facecolor=fig.get_facecolor())
    plt.close(fig)
    return out_path
