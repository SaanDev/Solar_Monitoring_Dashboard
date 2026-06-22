"""Download the burst-classifier checkpoint from a URL (Git LFS fallback).

The checkpoint normally ships in the repo via Git LFS at
backend/ml_model/best.pt — a clone with Git LFS installed already has it
(`git lfs pull`). This script is a fallback for environments WITHOUT Git LFS
(e.g. a "Download ZIP" that ships only LFS pointer files).

Usage
-----
From the repo root:

    python scripts/download_model.py

Or with an explicit URL / destination:

    python scripts/download_model.py \\
        --url https://example.com/best.pt \\
        --dest backend/ml_model/best.pt

Environment variables
---------------------
ML_MODEL_URL   — set in backend/.env; read automatically if --url is omitted.

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
_DEFAULT_DEST = _REPO_ROOT / "backend" / "ml_model" / "best.pt"
_ENV_FILE = _REPO_ROOT / "backend" / ".env"


def _read_env_url() -> str:
    """Read ML_MODEL_URL from the environment or backend/.env."""
    url = os.environ.get("ML_MODEL_URL", "").strip()
    if url:
        return url
    if _ENV_FILE.exists():
        for line in _ENV_FILE.read_text().splitlines():
            line = line.strip()
            if line.startswith("ML_MODEL_URL"):
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
    parser.add_argument("--url", default="", help="Direct download URL for best.pt")
    parser.add_argument(
        "--dest",
        default=str(_DEFAULT_DEST),
        help=f"Destination path (default: {_DEFAULT_DEST})",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-download even if the file already exists",
    )
    args = parser.parse_args()

    dest = Path(args.dest)
    if dest.exists() and not args.force:
        size_mb = dest.stat().st_size / 1_048_576
        print(f"Checkpoint already exists ({size_mb:.1f} MB): {dest}")
        print("Pass --force to re-download.")
        return

    url = args.url or _read_env_url()
    if not url:
        print(
            "Error: no URL supplied.\n"
            "  Set ML_MODEL_URL in backend/.env, or pass --url <url>.\n\n"
            "  Upload best.pt to a GitHub Release on your repo, then copy the\n"
            "  asset URL and either:\n"
            "    echo 'ML_MODEL_URL=<url>' >> backend/.env\n"
            "  or:\n"
            "    python scripts/download_model.py --url <url>",
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
