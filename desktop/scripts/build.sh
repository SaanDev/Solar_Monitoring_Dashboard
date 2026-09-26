#!/usr/bin/env bash
# Builds the Linux package: desktop/dist/SolarMonitoringDashboard-<version>-amd64.deb
# The Linux counterpart of build.ps1:
#
#   1. build-runtime.sh — bundled Python + backend + ML checkpoints (desktop/build/runtime)
#   2. frontend `npm run build:desktop` — static UI export (frontend/out)
#   3. electron-builder — Electron shell + .deb package (desktop/dist)
#
# Needs Linux x86_64 (WSL works), Node 20+, Git LFS checkpoints pulled (`git lfs pull`),
# and network access on the first run (Python, PyTorch CPU and the scientific stack are
# cached in desktop/build/cache afterwards). Don't run it while `next dev` serves from
# frontend/ on this machine: `next build` rewrites frontend/.next.
#
# Usage: desktop/scripts/build.sh [--skip-runtime] [--publish]
#
#   --skip-runtime  Reuse desktop/build/runtime from a previous build (UI/shell-only changes).
#   --publish       Upload the .deb + latest-linux.yml to a draft GitHub release v<version>
#                   instead of only building locally. Needs GH_TOKEN. CI normally does this.

set -euo pipefail

skip_runtime=0
publish=0
for arg in "$@"; do
  case "$arg" in
    --skip-runtime) skip_runtime=1 ;;
    --publish) publish=1 ;;
    -h | --help)
      sed -n '2,/^$/{s/^# \{0,1\}//;p}' "$0"
      exit 0
      ;;
    *)
      echo "unknown option: $arg (see --help)" >&2
      exit 2
      ;;
  esac
done

step() { printf '\033[36m==> %s\033[0m\n' "$*"; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DESKTOP_DIR="$(dirname "$SCRIPT_DIR")"
REPO_ROOT="$(dirname "$DESKTOP_DIR")"
FRONTEND_DIR="$REPO_ROOT/frontend"

if ((skip_runtime)); then
  if [[ ! -x "$DESKTOP_DIR/build/runtime/python/bin/python3" ]]; then
    echo "error: no staged Linux runtime in desktop/build/runtime - run without --skip-runtime first." >&2
    exit 1
  fi
else
  "$SCRIPT_DIR/build-runtime.sh"
fi

step "Frontend static export (frontend/out)"
[[ -d "$FRONTEND_DIR/node_modules" ]] || npm --prefix "$FRONTEND_DIR" ci
npm --prefix "$FRONTEND_DIR" run build:desktop

step "Electron shell + .deb package"
[[ -d "$DESKTOP_DIR/node_modules" ]] || npm --prefix "$DESKTOP_DIR" ci
if ((publish)); then
  npm --prefix "$DESKTOP_DIR" run release:linux
else
  npm --prefix "$DESKTOP_DIR" run dist:linux
fi

package="$(find "$DESKTOP_DIR/dist" -maxdepth 1 -name '*.deb' -printf '%T@ %p\n' | sort -n | tail -n 1 | cut -d' ' -f2-)"
step "Package: $package ($(du -h "$package" | cut -f1))"
