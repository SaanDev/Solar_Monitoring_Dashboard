"""Download a burst-classifier checkpoint from a URL (Git LFS fallback).

The checkpoints normally ship in the repo via Git LFS under backend/ml_model/ —
a clone with Git LFS installed already has them (`git lfs pull`). This script is
a fallback for environments WITHOUT Git LFS (e.g. a "Download ZIP" that ships
only LFS pointer files).

Three models ship: CCM v1.0.0 and v1.1.0 (binary burst / no-burst) and
CCMT v1.0.0 (burst type). Each has its own destination filename and its own
URL environment variable.

Usage
-----
From the repo root:

    python scripts/download_model.py                      # CCM v1.0.0
    python scripts/download_model.py --model ccm-1.1.0
    python scripts/download_model.py --model ccmt-1.0.0

Or with an explicit URL / destination:

    python scripts/download_model.py \\
        --url https://example.com/best.pt \\
        --dest backend/ml_model/best.pt

Environment variables (set in backend/.env; read when --url is omitted)
----------------------------------------------------------------------
ML_MODEL_URL        CCM v1.0.0  (backend/ml_model/best.pt)
ML_CCM_V110_URL     CCM v1.1.0  (backend/ml_model/ccm_v1_1_0.pt)
ML_CCMT_V100_URL    CCMT v1.0.0 (backend/ml_model/ccmt_v1_0_0.pt)

The script works standalone: it does NOT import from the backend package so it
can run before dependencies are installed (it only needs stdlib).
"""
from __future__ import annotations

import argparse
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

# ── Defaults ──────────────────────────────────────────────────────────────────
_REPO_ROOT = Path(__file__).resolve().parent.parent
_ML_DIR = _REPO_ROOT / "backend" / "ml_model"
_DEFAULT_DEST = _ML_DIR / "best.pt"
_ENV_FILE = _REPO_ROOT / "backend" / ".env"

# model id -> (destination filename, URL environment variable). Mirrors the
# registry in backend/app/ml/registry.py; keep the two in step.
_KNOWN: dict[str, tuple[str, str]] = {
    "ccm-1.0.0": ("best.pt", "ML_MODEL_URL"),
    "ccm-1.1.0": ("ccm_v1_1_0.pt", "ML_CCM_V110_URL"),
    "ccmt-1.0.0": ("ccmt_v1_0_0.pt", "ML_CCMT_V100_URL"),
}


def _read_env_url(var: str = "ML_MODEL_URL") -> str:
    """Read ``var`` from the environment or backend/.env."""
    url = os.environ.get(var, "").strip()
    if url:
        return url
    if _ENV_FILE.exists():
        for line in _ENV_FILE.read_text().splitlines():
            line = line.strip()
            if line.startswith(var):
                _, _, val = line.partition("=")
                return val.strip().strip('"').strip("'")
    return ""


class _Progress(urllib.request.BaseHandler):
    """Simple progress reporter for urllib.request.urlretrieve."""

    def __init__(self, total: int) -> None:
        self._total = total
        self._seen = 0
        self._last_pct = -1

    def update(self, count: int, block_size: int, _total: int) -> None:
        self._seen = min(count * block_size, self._total)
        pct = int(100 * self._seen / self._total) if self._total > 0 else 0
        if pct != self._last_pct:
            bar = "#" * (pct // 2) + "-" * (50 - pct // 2)
            mb = self._seen / 1_048_576
            total_mb = self._total / 1_048_576
            print(f"\r  [{bar}] {pct:3d}%  {mb:.1f}/{total_mb:.1f} MB", end="", flush=True)
            self._last_pct = pct
        if self._seen >= self._total:
            print()


def download(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(".tmp")
    print(f"Downloading from:\n  {url}")
    print(f"Saving to:\n  {dest}\n")
    try:
        # Get content length for progress display.
        with urllib.request.urlopen(url) as r:
            total = int(r.headers.get("Content-Length", 0))
        progress = _Progress(total)
        urllib.request.urlretrieve(url, tmp, reporthook=progress.update)
        tmp.rename(dest)
        size_mb = dest.stat().st_size / 1_048_576
        print(f"\nSaved {size_mb:.1f} MB → {dest}")
    except Exception:
        if tmp.exists():
            tmp.unlink(missing_ok=True)
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--model",
        choices=sorted(_KNOWN),
        default="ccm-1.0.0",
        help="Which model to fetch (default: ccm-1.0.0)",
    )
    parser.add_argument("--url", default="", help="Direct download URL for the checkpoint")
    parser.add_argument(
        "--dest",
        default="",
        help="Destination path (default: derived from --model)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-download even if the file already exists",
    )
    args = parser.parse_args()

    filename, url_var = _KNOWN[args.model]
    dest = Path(args.dest) if args.dest else _ML_DIR / filename
    if dest.exists() and not args.force:
        size_mb = dest.stat().st_size / 1_048_576
        print(f"Checkpoint already exists ({size_mb:.1f} MB): {dest}")
        print("Pass --force to re-download.")
        return

    url = args.url or _read_env_url(url_var)
    if not url:
        print(
            f"Error: no URL supplied for {args.model}.\n"
            f"  Set {url_var} in backend/.env, or pass --url <url>.\n\n"
            f"  Upload {filename} to a GitHub Release on your repo, then copy the\n"
            "  asset URL and either:\n"
            f"    echo '{url_var}=<url>' >> backend/.env\n"
            "  or:\n"
            f"    python scripts/download_model.py --model {args.model} --url <url>",
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        download(url, dest)
    except urllib.error.URLError as exc:
        print(f"Download failed: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
