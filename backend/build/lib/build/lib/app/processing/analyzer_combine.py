"""Combine multiple e-CALLISTO dynamic spectra in time or frequency.

Ported (and simplified for the web tool) from the desktop analyzer's
burst_processor.combine_time / combine_frequency. Operates on already-loaded
arrays rather than filenames:

- **Time combine**: files share a frequency axis and are consecutive in time.
  Segments are concatenated along the time axis; when observation start times are
  known the real inter-segment gaps are preserved.
- **Frequency combine**: files share a time axis and cover different frequency
  bands. Bands are placed on a regularized frequency grid (lowest-band-wins on
  overlap); uncovered grid rows are left as NaN (rendered as blank gaps).

Pure functions — no I/O.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import numpy as np


@dataclass
class CombineInput:
    data: np.ndarray          # (n_freq, n_time)
    freq_axis: np.ndarray     # MHz
    time_axis: np.ndarray     # seconds from this file's start
    obs_start: datetime | None


@dataclass
class CombineResult:
    data: np.ndarray
    freq_axis: np.ndarray
    time_axis: np.ndarray
    obs_start: datetime | None


def _axes_close(a: np.ndarray, b: np.ndarray, atol: float) -> bool:
    a = np.asarray(a, dtype=float).ravel()
    b = np.asarray(b, dtype=float).ravel()
    return a.shape == b.shape and bool(np.allclose(a, b, atol=atol, rtol=0.0))


def _orient_ascending(data: np.ndarray, freq: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    f = np.asarray(freq, dtype=float).ravel()
    if f.size > 1 and np.median(np.diff(f)) < 0:  # descending -> ascending
        return data[::-1, :], f[::-1]
    return data, f


def _orient_descending(data: np.ndarray, freq: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    f = np.asarray(freq, dtype=float).ravel()
    if f.size > 1 and np.median(np.diff(f)) > 0:  # ascending -> descending
        return data[::-1, :], f[::-1]
    return data, f


def combine_time(items: list[CombineInput]) -> CombineResult:
    if len(items) < 2:
        raise ValueError("Need at least 2 files to combine in time.")

    def sort_key(it: CombineInput) -> float:
        return it.obs_start.timestamp() if it.obs_start else float(it.time_axis[0])

    items = sorted(items, key=sort_key)
    # Orient every segment the same way and require a shared frequency axis.
    oriented = [_orient_descending(it.data, it.freq_axis) for it in items]
    ref_freq = oriented[0][1]
    for _, f in oriented:
        if not _axes_close(f, ref_freq, atol=0.05):
            raise ValueError(
                "Time combine requires the same frequency axis in every file."
            )

    have_obs = all(it.obs_start is not None for it in items)
    base = items[0].obs_start
    seg_data: list[np.ndarray] = []
    seg_time: list[np.ndarray] = []
    cursor = 0.0
    for i, (it, (data, _f)) in enumerate(zip(items, oriented)):
        local = np.asarray(it.time_axis, dtype=float)
        local = local - local[0]
        if have_obs:
            offset = (it.obs_start - base).total_seconds()
            seg_time.append(offset + local)
        elif i == 0:
            seg_time.append(local)
            cursor = float(local[-1])
        else:
            dt = float(np.median(np.diff(local))) if local.size > 1 else 1.0
            shifted = local + cursor + dt
            seg_time.append(shifted)
            cursor = float(shifted[-1])
        seg_data.append(np.asarray(data, dtype=np.float32))

    return CombineResult(
        data=np.concatenate(seg_data, axis=1),
        freq_axis=np.asarray(ref_freq, dtype=float).copy(),
        time_axis=np.concatenate(seg_time),
        obs_start=base,
    )


def combine_frequency(items: list[CombineInput]) -> CombineResult:
    if len(items) < 2:
        raise ValueError("Need at least 2 files to combine in frequency.")

    n_time = items[0].data.shape[1]
    for it in items:
        if it.data.shape[1] != n_time:
            raise ValueError(
                "Frequency combine requires the same number of time samples in every file."
            )

    blocks = [_orient_ascending(it.data, it.freq_axis) for it in items]
    blocks.sort(key=lambda b: float(b[1][0]))  # by band minimum frequency

    overall_min = min(float(f[0]) for _d, f in blocks)
    overall_max = max(float(f[-1]) for _d, f in blocks)
    if overall_max <= overall_min:
        raise ValueError("Combined frequency range must span more than one channel.")

    steps = [
        float(np.median(np.abs(np.diff(f))))
        for _d, f in blocks
        if f.size > 1 and np.isfinite(np.median(np.abs(np.diff(f)))) and np.median(np.abs(np.diff(f))) > 0
    ]
    grid_step = min(steps) if steps else 1.0
    grid_count = max(1, int(round((overall_max - overall_min) / grid_step)))
    grid = np.linspace(overall_min, overall_max, grid_count + 1)
    tol = grid_step * 0.25

    combined = np.full((grid.size, n_time), np.nan, dtype=np.float32)
    filled = np.zeros(grid.size, dtype=bool)

    for data, f in blocks:
        band_min, band_max = float(f[0]), float(f[-1])
        covered = (grid >= band_min - tol) & (grid <= band_max + tol)
        if not np.any(covered):
            continue
        if f.size == 1:
            positions = np.zeros(int(np.count_nonzero(covered)), dtype=int)
        else:
            midpoints = 0.5 * (f[:-1] + f[1:])
            positions = np.clip(np.searchsorted(midpoints, grid[covered], side="right"), 0, f.size - 1)
        target = np.flatnonzero(covered)
        write = ~filled[target]  # lowest band already placed wins on overlap
        if np.any(write):
            rows = target[write]
            combined[rows, :] = np.asarray(data, dtype=np.float32)[positions[write], :]
            filled[rows] = True

    # Descending frequency for display (high freq at top), matching e-CALLISTO.
    return CombineResult(
        data=combined[::-1, :],
        freq_axis=grid[::-1],
        time_axis=np.asarray(items[0].time_axis, dtype=float).copy(),
        obs_start=items[0].obs_start,
    )
