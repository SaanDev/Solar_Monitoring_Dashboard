#!/usr/bin/env bash
# Installs a built .deb the way a user would and checks that the app works:
# apt resolves its dependencies and runs the postinst, the installed app starts
# (headless, under Xvfb) and brings its bundled backend up from /opt, serves the
# UI, shuts the backend down cleanly on quit, and the package removes cleanly.
# Uses a throwaway HOME, so it never touches real app data.
#
# Needs apt and sudo (or root); installs xvfb if it's missing. CI runs it after
# building (.github/workflows/desktop-release.yml).
#
# Usage: desktop/scripts/test-deb.sh desktop/dist/SolarMonitoringDashboard-<version>-amd64.deb

set -euo pipefail

step() { printf '\033[36m==> %s\033[0m\n' "$*"; }
die() {
  printf '\033[31merror: %s\033[0m\n' "$*" >&2
  exit 1
}

(($# == 1)) && [[ -f "$1" ]] || die "usage: $0 path/to/package.deb"
deb="$(realpath "$1")"
package="$(dpkg-deb -f "$deb" Package)"
sudo=()
((EUID == 0)) || sudo=(sudo)
export DEBIAN_FRONTEND=noninteractive

step "Installing $(basename "$deb") ($package)"
"${sudo[@]}" apt-get update -qq
"${sudo[@]}" apt-get install -y -qq "$deb"
command -v xvfb-run >/dev/null || "${sudo[@]}" apt-get install -y -qq xvfb
exe="/usr/bin/$package"
[[ -x "$exe" ]] || die "$exe is missing"
[[ -f "/usr/share/applications/$package.desktop" ]] || die "no .desktop entry"
dpkg -s "$package" | grep -E '^(Version|Installed-Size|Depends):'

step "Launching the installed app"
get() { curl -fsS --noproxy '*' --max-time 5 "http://127.0.0.1:47800$1"; }
# The packaged backend only: python3 under /opt/<product>/resources.
backend_pattern="resources/python/bin/python3 -P -m app.desktop"
get /api/status >/dev/null 2>&1 && die "port 47800 is in use; quit the running dashboard first"
home="$(mktemp -d)"
display=99
while [[ -e "/tmp/.X11-unix/X$display" ]]; do display=$((display + 1)); done
Xvfb ":$display" -screen 0 1600x1000x24 -nolisten tcp >/dev/null 2>&1 &
xvfb=$!
app=""
# A killed app closes its backend's stdin lifeline, so the backend exits too.
cleanup() {
  if [[ -n "$app" ]]; then kill -KILL "$app" 2>/dev/null || true; fi
  kill "$xvfb" 2>/dev/null || true
  rm -rf "$home"
}
trap cleanup EXIT
sleep 1
# Electron refuses to run as root with its sandbox on (a root CI container).
flags=()
((EUID == 0)) && flags=(--no-sandbox)
env -u XDG_DATA_HOME -u XDG_CONFIG_HOME HOME="$home" DISPLAY=":$display" \
  "$exe" "${flags[@]}" >"$home/app-console.log" 2>&1 &
app=$!

data="$home/.local/share/SolarDashboard"
ready=0
for ((i = 0; i < 360; i++)); do # 180 s: first start creates the DB and loads the models
  kill -0 "$app" 2>/dev/null || break
  if get /api/status >/dev/null 2>&1; then
    ready=1
    break
  fi
  sleep 0.5
done
if ((!ready)); then
  tail -n 40 "$home/app-console.log" "$data"/logs/*.log 2>/dev/null || true
  die "the backend never answered on 127.0.0.1:47800"
fi
backend="$(pgrep -af -- "$backend_pattern" || true)"
echo "    backend: $backend"
[[ "$backend" == *" /opt/"* ]] || die "the backend isn't the bundled interpreter under /opt"
page="$(get / || true)"
grep -qi "<html" <<<"$page" || die "UI not served at /"
for ((i = 0; i < 60; i++)); do # the window opens once the backend is ready
  grep -q "backend ready at" "$data/logs/main.log" 2>/dev/null && break
  sleep 0.5
done
grep -q "backend ready at" "$data/logs/main.log" || die "the shell never saw the backend come up"
echo "    backend ready, UI served, data in $data"

step "Quitting"
kill -TERM "$app"
for ((i = 0; i < 60; i++)); do # before-quit gives the backend 10 s to stop
  kill -0 "$app" 2>/dev/null || break
  sleep 0.5
done
kill -0 "$app" 2>/dev/null && die "the app didn't quit on SIGTERM"
app=""
pgrep -f -- "$backend_pattern" >/dev/null && die "the backend outlived the app"
grep -q "backend stopped" "$data/logs/main.log" || die "the backend wasn't stopped cleanly"
echo "    app and backend exited cleanly"

step "Removing the package"
"${sudo[@]}" apt-get remove -y -qq "$package"
[[ ! -e "$exe" ]] || die "$exe is still there after removal"
echo "    removed; the user's data folder is left alone, as intended"
