"""Repack a CALLISTO Trainer checkpoint into the slim form the dashboard ships.

A trainer ``best.pt`` is ~134 MB because it also carries optimizer state, epoch
counters and per-epoch metrics. The dashboard loader only ever reads two keys
(``app/ml/inference.py``: ``checkpoint["config"]`` and
``checkpoint["model_state"]``), so keeping just those cuts each file to ~45 MB.
Worth doing, since the checkpoints ship in the repo via Git LFS and git is the
only sync between machines.

This docstring doubles as ``--help`` output, so it stays ASCII: the Windows
console is cp1252 and raises on characters outside it.

Usage
-----
From the repo root, with a Python that has torch installed (the CALLISTO Trainer
venv does; the dashboard's local venv may not):

    python scripts/repack_model.py --model ccm-1.1.0
    python scripts/repack_model.py --model ccmt-1.0.0
    python scripts/repack_model.py --all

Or point it at an arbitrary checkpoint:

    python scripts/repack_model.py \\
        --source "C:/path/to/outputs/binary_.../checkpoints/best.pt" \\
        --dest backend/ml_model/ccm_v1_1_0.pt

The printed summary (architecture, threshold, class map, station-vocab size) is
the check that the right run was repacked: verify it against the training report
before committing the file.

Environment variables
---------------------
CALLISTO_TRAINER_DIR   root of the CALLISTO Trainer project, when it is not at
                       ``~/Desktop/CALLISTO Trainer``.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parent.parent
_ML_DIR = _REPO_ROOT / "backend" / "ml_model"


def _trainer_root() -> Path:
    import os

    override = os.environ.get("CALLISTO_TRAINER_DIR", "").strip()
    if override:
        return Path(override)
    return Path.home() / "Desktop" / "CALLISTO Trainer"


# model id -> (trainer run directory, destination filename)
_KNOWN: dict[str, tuple[str, str]] = {
    "ccm-1.1.0": ("binary_20260730_140730", "ccm_v1_1_0.pt"),
    "ccmt-1.0.0": ("type_20260730_141805", "ccmt_v1_0_0.pt"),
}


def _resolve(model_id: str) -> tuple[Path, Path]:
    run_dir, dest_name = _KNOWN[model_id]
    source = _trainer_root() / "outputs" / run_dir / "checkpoints" / "best.pt"
    return source, _ML_DIR / dest_name


# ── Summary ───────────────────────────────────────────────────────────────────


def _describe(config: dict[str, Any], state: dict[str, Any]) -> None:
    model_cfg = config.get("model", {}) or {}
    data_cfg = config.get("data", {}) or {}
    training_cfg = config.get("training", {}) or {}
    prep_cfg = config.get("preprocessing", {}) or {}

    print("  architecture      :", model_cfg.get("name"))
    print("  in_channels       :", model_cfg.get("in_channels"))
    print("  num_classes       :", model_cfg.get("num_classes", 1))
    print("  use_metadata      :", bool(model_cfg.get("use_metadata", False)))
    print("  use_physics       :", bool(model_cfg.get("use_physics", False)))
    vocab = model_cfg.get("station_vocab") or {}
    print(f"  station_vocab     : {len(vocab)} stations")
    print("  target_shape      :", data_cfg.get("target_shape"))
    print("  background_method :", prep_cfg.get("background_method"))
    print("  normalization     :", prep_cfg.get("normalization"),
          f"[{prep_cfg.get('db_vmin')}, {prep_cfg.get('db_vmax')}]")
    print("  threshold         :", training_cfg.get("threshold"))
    classes = data_cfg.get("classes") or {}
    if classes:
        ordered = sorted(classes.items(), key=lambda kv: int(kv[1]))
        print("  classes           :", ", ".join(f"{i}={name}" for name, i in ordered))
    print(f"  state_dict keys   : {len(state)}")
    # The head shape is the quickest confirmation of binary vs multi-class.
    for key in ("classifier.1.weight", "fc.weight"):
        if key in state:
            print(f"  head              : {key} {tuple(state[key].shape)}")


# ── Repack ────────────────────────────────────────────────────────────────────


def repack(source: Path, dest: Path, force: bool = False) -> None:
    import torch

    if not source.exists():
        raise FileNotFoundError(f"source checkpoint not found: {source}")
    if dest.exists() and not force:
        size_mb = dest.stat().st_size / 1_048_576
        print(f"Already repacked ({size_mb:.1f} MB): {dest}")
        print("Pass --force to overwrite.")
        return

    print(f"Reading {source}")
    checkpoint = torch.load(source, map_location="cpu", weights_only=False)
    for key in ("model_state", "config"):
        if key not in checkpoint:
            raise KeyError(
                f"{source} has no '{key}' — is this a CALLISTO Trainer checkpoint? "
                f"(found keys: {sorted(checkpoint)})"
            )

    config = checkpoint["config"]
    state = checkpoint["model_state"]
    _describe(config, state)

    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(".tmp")
    try:
        torch.save({"model_state": state, "config": config}, tmp)
        tmp.replace(dest)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise

    before = source.stat().st_size / 1_048_576
    after = dest.stat().st_size / 1_048_576
    # ASCII only: the Windows console is cp1252 and would fail on an arrow glyph.
    print(f"  -> {dest}")
    print(f"  {before:.1f} MB -> {after:.1f} MB ({100 * after / before:.0f}%)\n")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--model",
        choices=sorted(_KNOWN),
        help="Repack a known model by id (resolves the trainer run and destination)",
    )
    parser.add_argument("--all", action="store_true", help="Repack every known model")
    parser.add_argument("--source", help="Path to a trainer best.pt (with --dest)")
    parser.add_argument("--dest", help="Destination .pt path (with --source)")
    parser.add_argument("--force", action="store_true", help="Overwrite an existing file")
    args = parser.parse_args()

    if args.source or args.dest:
        if not (args.source and args.dest):
            parser.error("--source and --dest must be given together")
        jobs = [(Path(args.source), Path(args.dest))]
    elif args.all:
        jobs = [_resolve(model_id) for model_id in sorted(_KNOWN)]
    elif args.model:
        jobs = [_resolve(args.model)]
    else:
        parser.error("pass --model <id>, --all, or --source/--dest")

    try:
        for source, dest in jobs:
            repack(source, dest, force=args.force)
    except ImportError:
        print(
            "Error: torch is not installed in this interpreter.\n"
            "  Run with the CALLISTO Trainer venv, e.g.\n"
            '    "$HOME/Desktop/CALLISTO Trainer/.venv/Scripts/python" '
            "scripts/repack_model.py --all",
            file=sys.stderr,
        )
        sys.exit(1)
    except (FileNotFoundError, KeyError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
