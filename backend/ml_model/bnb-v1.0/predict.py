"""Standalone inference for an exported CALLISTO Trainer model.

Depends only on numpy, astropy and torch -- none of the training project.

    python predict.py path/to/file.fit.gz
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import torch
from astropy.io import fits

BUNDLE = Path(__file__).resolve().parent
CARD = json.loads((BUNDLE / "model_card.json").read_text(encoding="utf-8"))

DB_VMIN = float(CARD["preprocessing"]["db_vmin"])
DB_VMAX = float(CARD["preprocessing"]["db_vmax"])
TARGET = tuple(CARD["input"]["shape"][1:])
PLOTUTIL_DB_SCALE = 2500.0 / 255.0 / 25.4


def read_spectrum(path):
    """Primary HDU as [frequency, time] float32."""
    with fits.open(path, memmap=False) as hdul:
        return np.squeeze(np.asarray(hdul[0].data, dtype=np.float32))


def normalize(spectrum):
    """clean -> per-frequency median subtract -> dB window -> [0,1].

    Must be run on the WHOLE file before any cropping (see model_card.json).
    """
    data = np.asarray(spectrum, dtype=np.float32)
    finite = np.isfinite(data)
    if finite.any():
        data = np.where(finite, data, np.median(data[finite])).astype(np.float32)
    else:
        data = np.zeros_like(data)
    data = (data - np.median(data, axis=1, keepdims=True)) * np.float32(PLOTUTIL_DB_SCALE)
    return np.clip((data - DB_VMIN) / (DB_VMAX - DB_VMIN), 0.0, 1.0).astype(np.float32)


def normalize_quiet(spectrum):
    """As normalize(), but each channel's background is its quiet part.

    Needed only by a model whose views include "quiet_context".
    """
    percentile = float(CARD.get("scope", {}).get("quiet_percentile") or 10.0)
    data = np.asarray(spectrum, dtype=np.float32)
    finite = np.isfinite(data)
    if finite.any():
        data = np.where(finite, data, np.median(data[finite])).astype(np.float32)
    else:
        data = np.zeros_like(data)
    baseline = np.percentile(data, percentile, axis=1, keepdims=True).astype(np.float32)
    data = ((data - baseline).astype(np.float32) * np.float32(PLOTUTIL_DB_SCALE)).astype(np.float32)
    return np.clip((data - DB_VMIN) / (DB_VMAX - DB_VMIN), 0.0, 1.0).astype(np.float32)


def _resize_axis(data, new_size, axis):
    old = data.shape[axis]
    if old == new_size:
        return data.astype(np.float32, copy=False)
    pos = (np.arange(new_size, dtype=np.float64) * (old - 1) / (new_size - 1)
           if new_size > 1 and old > 1 else np.zeros(new_size))
    lo = np.clip(np.floor(pos).astype(np.intp), 0, old - 1)
    hi = np.minimum(lo + 1, old - 1)
    frac = (pos - lo).astype(np.float32)
    if axis == 1:
        return (data[:, lo] * (1 - frac[None, :]) + data[:, hi] * frac[None, :]).astype(np.float32)
    return (data[lo, :] * (1 - frac[:, None]) + data[hi, :] * frac[:, None]).astype(np.float32)


def resize(spectrum, target=TARGET):
    data = _resize_axis(np.asarray(spectrum, dtype=np.float32), int(target[1]), axis=1)
    return _resize_axis(data, int(target[0]), axis=0)


VIEWS = list(CARD.get("input", {}).get("views") or ["crop"])
CONTEXT_MIN_PAD = int(CARD.get("scope", {}).get("context_min_pad_cols") or 240)


def _max_pool(data, target, axis):
    factor = data.shape[axis] // max(1, int(target))
    if factor < 2:
        return data
    blocks = int(np.ceil(data.shape[axis] / factor))
    pad = blocks * factor - data.shape[axis]
    if pad:
        widths = [(0, 0), (0, 0)]
        widths[axis] = (0, pad)
        data = np.pad(data, widths, mode="edge")
    if axis == 1:
        return data.reshape(data.shape[0], blocks, factor).max(axis=2)
    return data.reshape(blocks, factor, data.shape[1]).max(axis=1)


def context_view(normalized, box):
    """Full band, the region's columns widened each side, max-pooled then resized."""
    r0, r1, c0, c1 = box
    n_time = normalized.shape[1]
    pad = max(c1 - c0, CONTEXT_MIN_PAD)
    width = min(c1 - c0 + 2 * pad, n_time)
    lo = min(max(0, c0 - pad), n_time - width)
    patch = normalized[:, lo:lo + width]
    patch = _max_pool(_max_pool(patch, TARGET[1], 1), TARGET[0], 0)
    return resize(patch)


def to_tensor(normalized, box=None, quiet=None):
    """Whole file, or one [row0, row1, col0, col1] region with the trained views.

    ``quiet`` is normalize_quiet() of the same file, required when the views
    include "quiet_context".
    """
    if box is None:
        return resize(normalized)[np.newaxis, np.newaxis]
    margin = float(CARD.get("scope", {}).get("context_margin") or 0.0)
    r0, r1, c0, c1 = box
    dr, dc = int(round((r1 - r0) * margin)), int(round((c1 - c0) * margin))
    r0, r1 = max(0, r0 - dr), min(normalized.shape[0], r1 + dr)
    c0, c1 = max(0, c0 - dc), min(normalized.shape[1], c1 + dc)
    layers = [resize(normalized[r0:r1, c0:c1])]
    if "context" in VIEWS:
        layers.append(context_view(normalized, box))
    if "quiet_context" in VIEWS:
        if quiet is None:
            raise ValueError("this model's views include quiet_context: pass quiet=normalize_quiet(spectrum)")
        layers.append(context_view(quiet, box))
    return np.stack(layers)[np.newaxis]


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 1

    model = torch.jit.load(str(BUNDLE / "model_scripted.pt"), map_location="cpu")
    model.eval()

    normalized = normalize(read_spectrum(sys.argv[1]))
    tensor = torch.from_numpy(to_tensor(normalized))
    if len(VIEWS) > 1:
        # A multi-view region model given a whole file: repeat the one view so
        # the shapes line up. The result is out of distribution (see below).
        tensor = tensor.repeat(1, len(VIEWS), 1, 1)

    inputs = [tensor]
    physics_spec = CARD.get("physics_input")
    if physics_spec:
        # Zeros mean "no measurement available", which the model was trained to
        # handle -- see the note in model_card.json. Measuring the drift rate
        # properly requires the project's burst_physics module.
        inputs.append(torch.zeros(1, int(physics_spec["shape"][0])))

    with torch.no_grad():
        logits = model(*inputs)

    if CARD["output"]["head"] == "sigmoid":
        probability = float(torch.sigmoid(logits.reshape(-1))[0])
        threshold = float(CARD["output"]["decision_threshold"])
        label = "Burst" if probability >= threshold else "No_Burst"
        print(json.dumps({"file": sys.argv[1], "predicted_label": label,
                          "burst_probability": probability,
                          "decision_threshold": threshold}, indent=2))
    else:
        probs = torch.softmax(logits.reshape(1, -1), dim=1)[0].numpy()
        names = list(CARD["classes"])
        values = {n: float(p) for n, p in zip(names, probs)}
        # RFI and No_Burst are reported as one "not a burst" (the model keeps
        # them apart only because training them apart cut false alarms).
        if "RFI" in values and "No_Burst" in values:
            values["No_Burst"] += values.pop("RFI")
        best = max(values, key=values.get)
        result = {"file": sys.argv[1], "burst_type": best,
                  "confidence": values[best], "probabilities": values}
        # This model was trained on crops around a single burst. Handed a whole
        # recording it will still answer, confidently and meaninglessly, so say
        # so rather than let the number be quoted.
        if "CROP" in CARD.get("scope", {}).get("operates_on", ""):
            result["warning"] = (
                "Run on the WHOLE file, but this model expects a crop around one "
                "burst. Locate a region first and pass box=(row0,row1,col0,col1) "
                "to to_tensor(); this result is out of distribution."
            )
        if CARD.get("physics_input"):
            result["physics"] = "not measured (zeros passed; see model_card.json)"
            if CARD["physics_input"].get("feature_set", "physics_v1") != "physics_v1":
                result["warning"] = result.get("warning", "") + (
                    " This model's region features cannot be computed without the "
                    "CALLISTO Trainer project; zeros are out of distribution. Use the "
                    "project's CascadePredictor for real predictions."
                )
        print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
