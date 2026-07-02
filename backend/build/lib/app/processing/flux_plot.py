"""Server-side matplotlib renderers for GOES flux time series (downloadable PNGs).

Uses the object-oriented Figure/Agg API (no pyplot global state) and mirrors the
dark dashboard theme + flare-class bands used by the frontend Plotly charts.
"""
from __future__ import annotations

from datetime import datetime
from io import BytesIO

import matplotlib.dates as mdates
import numpy as np
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure

_BG = "#0f1117"
_PLOT_BG = "#0a0d14"
_FG = "#94a3b8"
_GRID = "#1e2535"

# Flare-class decade bands for the XRS long channel (W/m²).
_FLARE_BANDS = [
    (1e-8, 1e-7, "A", "#334155"),
    (1e-7, 1e-6, "B", "#3b4a5e"),
    (1e-6, 1e-5, "C", "#374151"),
    (1e-5, 1e-4, "M", "#44394d"),
    (1e-4, 1e-3, "X", "#4c2626"),
]


def _new_axes(title: str, ylabel: str, log: bool = True):
    fig = Figure(figsize=(9, 4.5), dpi=120)
    fig.patch.set_facecolor(_BG)
    FigureCanvasAgg(fig)
    ax = fig.subplots()
    ax.set_facecolor(_PLOT_BG)
    if log:
        ax.set_yscale("log")
    ax.set_title(title, color="#e2e8f0", fontsize=12, pad=8)
    ax.set_xlabel("Time (UTC)", color=_FG, fontsize=10)
    ax.set_ylabel(ylabel, color=_FG, fontsize=10)
    ax.tick_params(colors=_FG, labelsize=9)
    ax.grid(True, color=_GRID, linewidth=0.6, alpha=0.6)
    for spine in ax.spines.values():
        spine.set_edgecolor(_GRID)
    return fig, ax


def _format_time_axis(ax) -> None:
    loc = mdates.AutoDateLocator()
    ax.xaxis.set_major_locator(loc)
    ax.xaxis.set_major_formatter(mdates.ConciseDateFormatter(loc))


def _naive_utc(t: datetime) -> datetime:
    return t.replace(tzinfo=None)


def _series(points, attr) -> list[float]:
    return [getattr(p, attr) if getattr(p, attr) is not None else np.nan for p in points]


def _empty(ax) -> None:
    ax.text(0.5, 0.5, "No data in range", transform=ax.transAxes,
            ha="center", va="center", color=_FG, fontsize=12)


def _to_png(fig) -> bytes:
    buf = BytesIO()
    fig.savefig(buf, format="png", facecolor=fig.get_facecolor(), bbox_inches="tight")
    return buf.getvalue()


def render_xrs_png(points, title: str = "GOES X-ray Flux") -> bytes:
    fig, ax = _new_axes(title, "Flux (W/m²)")
    ax.set_ylim(1e-9, 1e-3)
    if points:
        times = [_naive_utc(p.time) for p in points]
        for lo, hi, label, color in _FLARE_BANDS:
            ax.axhspan(lo, hi, facecolor=color, alpha=0.3, linewidth=0)
            ax.text(1.005, (lo * hi) ** 0.5, label, transform=ax.get_yaxis_transform(),
                    color="#64748b", fontsize=9, va="center")
        ax.plot(times, _series(points, "long_channel"), color="#ef4444", lw=1.3,
                label="0.1–0.8 nm (long)")
        ax.plot(times, _series(points, "short_channel"), color="#3b82f6", lw=1.3,
                label="0.05–0.4 nm (short)")
        ax.legend(loc="upper left", fontsize=9, facecolor=_PLOT_BG, edgecolor=_GRID,
                  labelcolor=_FG)
        _format_time_axis(ax)
    else:
        _empty(ax)
    return _to_png(fig)


def render_proton_png(points, title: str = "GOES Proton Flux") -> bytes:
    fig, ax = _new_axes(title, "Particles / (cm² s sr)")
    ax.set_ylim(1e-2, 1e4)
    if points:
        times = [_naive_utc(p.time) for p in points]
        # S1 radiation-storm threshold (10 pfu at ≥10 MeV).
        ax.axhline(10, color="#ef4444", lw=1, ls=":", alpha=0.8)
        ax.plot(times, _series(points, "flux_gt10"), color="#f97316", lw=1.3, label="≥10 MeV")
        ax.plot(times, _series(points, "flux_gt50"), color="#a855f7", lw=1.3, label="≥50 MeV")
        ax.plot(times, _series(points, "flux_gt100"), color="#ef4444", lw=1.3, label="≥100 MeV")
        ax.legend(loc="upper left", fontsize=9, facecolor=_PLOT_BG, edgecolor=_GRID,
                  labelcolor=_FG)
        _format_time_axis(ax)
    else:
        _empty(ax)
    return _to_png(fig)


def _kp_color(kp: float) -> str:
    if kp >= 7:
        return "#ef4444"  # G3+ severe
    if kp >= 6:
        return "#f97316"  # G2
    if kp >= 5:
        return "#eab308"  # G1 minor storm
    if kp >= 4:
        return "#22c55e"  # active
    return "#3b82f6"      # quiet


def render_kp_png(points, title: str = "Kp Index") -> bytes:
    fig, ax = _new_axes(title, "Kp", log=False)
    ax.set_ylim(0, 9)
    if points:
        times = [_naive_utc(p.time) for p in points]
        values = [p.kp for p in points]
        colors = [_kp_color(v) for v in values]
        ax.bar(times, values, width=(3 / 24) * 0.85, color=colors, edgecolor="none", align="center")
        ax.axhline(5, color="#ef4444", lw=1, ls=":", alpha=0.8)  # G1 storm threshold
        _format_time_axis(ax)
    else:
        _empty(ax)
    return _to_png(fig)


def render_dst_png(points, title: str = "Dst Index") -> bytes:
    fig, ax = _new_axes(title, "Dst (nT)", log=False)
    if points:
        times = [_naive_utc(p.time) for p in points]
        ax.plot(times, [p.dst for p in points], color="#22c55e", lw=1.3)
        ax.axhline(0, color="#475569", lw=0.8)
        ax.axhline(-50, color="#eab308", lw=0.8, ls=":", alpha=0.7)   # moderate storm
        ax.axhline(-100, color="#f97316", lw=0.8, ls=":", alpha=0.7)  # intense storm
        _format_time_axis(ax)
    else:
        _empty(ax)
    return _to_png(fig)
