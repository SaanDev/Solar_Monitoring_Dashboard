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
