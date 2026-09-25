#!/usr/bin/env bash
# Stages the Python runtime the Linux desktop app ships: desktop/build/runtime/{python,backend}.
# The Linux counterpart of build-runtime.ps1: same steps, same layout.
#
#   1. Downloads a pinned, relocatable CPython (python-build-standalone) and checks its SHA-256.
#   2. Installs the backend's dependencies into it from desktop/requirements-linux.lock.txt
#      (PyTorch from the CPU-only index: no CUDA libraries, several GB smaller).
#   3. Copies the backend source (app/, alembic/) and the ML checkpoints next to it.
#   4. Byte-compiles everything with unchecked-hash .pyc files, so the installed app
#      never recompiles (the .deb installs under /opt, which the app can't write to,
#      and cold imports of the scientific stack are slow).
#   5. Smoke-tests the result: imports, all three ML models, and a real start/stop of
#      `python -m app.desktop`.
#
# Usage: desktop/scripts/build-runtime.sh [--refresh-lock] [--skip-smoke-test]
#
#   --refresh-lock     Re-resolve the dependencies from backend/pyproject.toml ([ml,desktop]
#                      extras) and rewrite desktop/requirements-linux.lock.txt. Versions are
#                      held to the Windows lock (requirements.lock.txt), so refresh that one
#                      first; only Linux-only packages are resolved fresh. Commit the new
#                      lock deliberately.
#   --skip-smoke-test  Skip step 5 (not recommended).

set -euo pipefail

refresh_lock=0
smoke_test=1
for arg in "$@"; do
  case "$arg" in
    --refresh-lock) refresh_lock=1 ;;
    --skip-smoke-test) smoke_test=0 ;;
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
die() {
  printf '\033[31merror: %s\033[0m\n' "$*" >&2
  exit 1
}

[[ "$(uname -s)" == Linux && "$(uname -m)" == x86_64 ]] || die "builds the Linux x86_64 runtime; run it on Linux x86_64"

DESKTOP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPO_ROOT="$(dirname "$DESKTOP_DIR")"
BUILD_DIR="$DESKTOP_DIR/build"
RUNTIME="$BUILD_DIR/runtime"
PY_DIR="$RUNTIME/python"
PY="$PY_DIR/bin/python3"
BACKEND_SRC="$REPO_ROOT/backend"
BACKEND_OUT="$RUNTIME/backend"
CACHE="$BUILD_DIR/cache"
LOCK="$DESKTOP_DIR/requirements-linux.lock.txt"
WINDOWS_LOCK="$DESKTOP_DIR/requirements.lock.txt"

# Pinned interpreter: the same Python and python-build-standalone release as
# build-runtime.ps1. The "stripped" build only drops debug symbols.
PBS_RELEASE="20260924"
PY_VERSION="3.13.15"
PBS_FILE="cpython-$PY_VERSION+$PBS_RELEASE-x86_64-unknown-linux-gnu-install_only_stripped.tar.gz"
PBS_URL="https://github.com/astral-sh/python-build-standalone/releases/download/$PBS_RELEASE/cpython-$PY_VERSION%2B$PBS_RELEASE-x86_64-unknown-linux-gnu-install_only_stripped.tar.gz"
PBS_SHA256="d0b640eed27fbdd6f5f2bd33444aee53df2c8863f8b2a96f4094717411e3de9c"
TORCH_INDEX="https://download.pytorch.org/whl/cpu"

export PIP_CACHE_DIR="$CACHE/pip"
export PIP_DISABLE_PIP_VERSION_CHECK=1
# The runtime is a private staging tree, not the system Python.
export PIP_ROOT_USER_ACTION=ignore
export PYTHONNOUSERSITE=1
unset PYTHONHOME PYTHONPATH VIRTUAL_ENV CONDA_PREFIX
PIP_INSTALL=(-m pip install --no-warn-script-location)

# Copies a directory tree, dropping every subdirectory with one of the given names.
copy_tree() {
  local from="$1" to="$2" name
  shift 2
  mkdir -p "$to"
  cp -R "$from/." "$to/"
  for name in "$@"; do
    find "$to" -type d -name "$name" -prune -exec rm -rf {} +
  done
}

# ── 1. Interpreter ────────────────────────────────────────────────────────────
step "Python $PY_VERSION (python-build-standalone $PBS_RELEASE)"
mkdir -p "$CACHE"
archive="$CACHE/$PBS_FILE"
if [[ ! -f "$archive" ]]; then
  curl -fL --retry 3 --silent --show-error -o "$archive.part" "$PBS_URL"
  mv "$archive.part" "$archive"
fi
actual="$(sha256sum "$archive" | cut -d' ' -f1)"
if [[ "$actual" != "$PBS_SHA256" ]]; then
  rm -f "$archive"
  die "SHA-256 mismatch for $PBS_FILE (got $actual)"
fi
rm -rf "$RUNTIME"
mkdir -p "$RUNTIME"
# The archive's top-level folder is python/ -> build/runtime/python.
tar -xzf "$archive" -C "$RUNTIME"
"$PY" -c "import sys; print(sys.version)"

# ── 2. Dependencies ───────────────────────────────────────────────────────────
if ((refresh_lock)) || [[ ! -f "$LOCK" ]]; then
  step "Resolving dependencies from backend/pyproject.toml -> requirements-linux.lock.txt"
  # Hold every package both platforms share to the Windows lock's version, so the
  # two builds ship the same stack. Its option lines aren't constraints.
  constraints="$BUILD_DIR/windows-constraints.txt"
  grep -v -e '^#' -e '^--' "$WINDOWS_LOCK" >"$constraints"
  # torch first, from the CPU index, so the [ml] extra is already satisfied by it.
  "$PY" "${PIP_INSTALL[@]}" torch torchvision --index-url "$TORCH_INDEX" -c "$constraints"
  # Resolve from a lone copy of pyproject.toml: building the real backend/ tree
  # would make setuptools leave build/ and *.egg-info litter in the repo. Only
  # the dependency list matters here — the backend ships as source (step 3).
  lock_project="$BUILD_DIR/lock-project"
  rm -rf "$lock_project"
  mkdir -p "$lock_project"
  cp "$BACKEND_SRC/pyproject.toml" "$lock_project/"
  "$PY" "${PIP_INSTALL[@]}" "${lock_project}[ml,desktop]" -c "$constraints"
  "$PY" -m pip uninstall -y space-weather-backend
  {
    echo "# Pinned dependencies of the desktop app's bundled Python ($PY_VERSION, linux x86_64)."
    echo "# Generated by desktop/scripts/build-runtime.sh --refresh-lock from backend/pyproject.toml"
    echo "# extras [ml,desktop], held to the versions in requirements.lock.txt (the Windows lock)"
    echo "# so both builds ship the same packages. Refresh deliberately; don't hand-edit."
    echo "--extra-index-url $TORCH_INDEX"
    "$PY" -m pip freeze
  } >"$LOCK.tmp"
  mv "$LOCK.tmp" "$LOCK"
else
  step "Installing dependencies from requirements-linux.lock.txt"
  "$PY" "${PIP_INSTALL[@]}" -r "$LOCK"
fi
"$PY" -m pip check

# ── 3. Backend source + checkpoints ───────────────────────────────────────────
step "Copying backend source and ML checkpoints"
copy_tree "$BACKEND_SRC/app" "$BACKEND_OUT/app" tests __pycache__
copy_tree "$BACKEND_SRC/alembic" "$BACKEND_OUT/alembic" __pycache__
mkdir -p "$BACKEND_OUT/ml_model"
for pt in "$BACKEND_SRC"/ml_model/*.pt; do
  [[ -e "$pt" ]] || die "no checkpoints in backend/ml_model - run 'git lfs pull' first"
  # An un-pulled Git LFS pointer is a ~130-byte text file, not a model.
  (($(stat -c %s "$pt") >= 1048576)) || die "$(basename "$pt") is a Git LFS pointer - run 'git lfs pull' first"
  cp "$pt" "$BACKEND_OUT/ml_model/"
done

# ── 4. Trim + byte-compile ────────────────────────────────────────────────────
step "Trimming build-only files"
# C++ headers, CMake files and static libraries are only for compiling torch extensions.
site_packages="$("$PY" -c "import sysconfig; print(sysconfig.get_path('purelib'))")"
rm -rf "$site_packages/torch/include" "$site_packages/torch/share"
find "$site_packages/torch/lib" -maxdepth 1 -name '*.a' -delete 2>/dev/null || true
# Package test suites stay: some packages (astropy) import their tests module at import time.

step "Byte-compiling (unchecked-hash .pyc)"
# Exit code is non-zero if any single file fails to compile (e.g. deliberately
# broken test fixtures inside packages); those files are simply never imported.
if ! "$PY" -m compileall -q -f -j 0 --invalidation-mode unchecked-hash "$PY_DIR/lib" "$BACKEND_OUT" >/dev/null; then
  echo "warning: compileall reported files it could not compile (usually harmless test fixtures)" >&2
fi

# The package installs these files as root; every user must be able to read
# them, whatever umask the build ran under.
chmod -R u+rwX,go+rX,go-w "$RUNTIME"

# ── 5. Smoke test ─────────────────────────────────────────────────────────────
if ((smoke_test)); then
  step "Smoke test: imports and ML checkpoints"
  PYTHONPATH="$BACKEND_OUT" "$PY" -P - <<'EOF'
import torch, sunpy, sunpy.map, astropy, aiapy, drms, reproject, imageio_ffmpeg, aiosqlite, scipy
from app.ml import registry
from app.ml.inference import get_loaded
for spec in registry._SPECS.values():
    assert registry.is_available(spec), f"{spec.id}: checkpoint missing"
    assert get_loaded(spec) is not None, f"{spec.id}: failed to load"
print("torch", torch.__version__, "| sunpy", sunpy.__version__, "| models OK:", ", ".join(registry._SPECS))
EOF

  step "Smoke test: start and stop the desktop backend"
  smoke_home="$BUILD_DIR/smoke-home"
  rm -rf "$smoke_home"
  mkdir -p "$smoke_home"
  port=47899
  frontend="$REPO_ROOT/frontend/out"
  frontend_env=()
  [[ -d "$frontend" ]] && frontend_env=("SWD_FRONTEND_DIR=$frontend")
  # The backend's stdin is its lifeline, as under Electron: a FIFO we hold open.
  fifo="$smoke_home/lifeline"
  mkfifo "$fifo"
  env PYTHONPATH="$BACKEND_OUT" PYTHONUTF8=1 SWD_HOME="$smoke_home" SWD_PORT="$port" \
    SWD_LIFELINE=stdin ENABLE_SCHEDULER=false "${frontend_env[@]}" \
    "$PY" -P -m app.desktop <"$fifo" >"$smoke_home/console.log" 2>&1 &
  pid=$!
  exec {lifeline}>"$fifo"
  trap 'kill "$pid" 2>/dev/null || true' EXIT

  get() { curl -fsS -o /dev/null --noproxy '*' --max-time "$1" "http://127.0.0.1:$port$2"; }
  ready=0
  for ((i = 0; i < 360; i++)); do # 180 s
    kill -0 "$pid" 2>/dev/null || break
    if get 3 /api/status 2>/dev/null; then
      ready=1
      break
    fi
    sleep 0.5
  done
  ((ready)) || die "desktop backend did not become ready (see $smoke_home/logs/backend.log, $smoke_home/console.log)"
  if [[ -d "$frontend" ]]; then
    get 10 / || die "UI not served at /"
  fi

  echo quit >&"$lifeline"
  exec {lifeline}>&-
  for ((i = 0; i < 40; i++)); do # 20 s
    kill -0 "$pid" 2>/dev/null || break
    sleep 0.5
  done
  kill -0 "$pid" 2>/dev/null && die "backend ignored the quit on its lifeline"
  code=0
  wait "$pid" || code=$?
  trap - EXIT
  ((code == 0)) || die "backend exited with code $code (see $smoke_home/console.log)"
  echo "    backend started, served /api/status$([[ -d "$frontend" ]] && echo ' and /'), and shut down cleanly"
fi

step "Runtime ready: $RUNTIME ($(du -sh "$RUNTIME" | cut -f1))"
