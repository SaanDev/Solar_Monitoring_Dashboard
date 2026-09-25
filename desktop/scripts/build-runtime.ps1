<#
.SYNOPSIS
  Stages the Python runtime the desktop app ships: desktop/build/runtime/{python,backend}.

.DESCRIPTION
  1. Downloads a pinned, relocatable CPython (python-build-standalone) and checks its SHA-256.
  2. Installs the backend's dependencies into it from desktop/requirements.lock.txt
     (PyTorch from the CPU-only index: no GPU in the desktop build, ~2 GB smaller).
  3. Copies the backend source (app/, alembic/) and the ML checkpoints next to it.
  4. Byte-compiles everything with unchecked-hash .pyc files, so the installed app
     never recompiles (its install dir isn't necessarily writable, and cold imports
     of the scientific stack are slow).
  5. Smoke-tests the result: imports, all three ML models, and a real start/stop of
     `python -m app.desktop`.

.PARAMETER RefreshLock
  Re-resolve the dependencies from backend/pyproject.toml ([ml,desktop] extras) and
  rewrite desktop/requirements.lock.txt. Commit the new lock deliberately.

.PARAMETER SkipSmokeTest
  Skip step 5 (not recommended).
#>
param(
  [switch]$RefreshLock,
  [switch]$SkipSmokeTest
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"  # PS 5.1's progress bar makes downloads crawl

$DesktopDir = Split-Path -Parent $PSScriptRoot
$RepoRoot = Split-Path -Parent $DesktopDir
$BuildDir = Join-Path $DesktopDir "build"
$Runtime = Join-Path $BuildDir "runtime"
$PyDir = Join-Path $Runtime "python"
$Py = Join-Path $PyDir "python.exe"
$BackendSrc = Join-Path $RepoRoot "backend"
$BackendOut = Join-Path $Runtime "backend"
$Cache = Join-Path $BuildDir "cache"
$Lock = Join-Path $DesktopDir "requirements.lock.txt"

# Pinned interpreter. Python 3.13: the current sunpy/numpy/scipy/aiapy need >= 3.12.
$PbsRelease = "20260924"
$PyVersion = "3.13.15"
$PbsFile = "cpython-$PyVersion+$PbsRelease-x86_64-pc-windows-msvc-install_only.tar.gz"
$PbsUrl = "https://github.com/astral-sh/python-build-standalone/releases/download/$PbsRelease/cpython-$PyVersion%2B$PbsRelease-x86_64-pc-windows-msvc-install_only.tar.gz"
$PbsSha256 = "cc5e5a61adbe02ae93e01a90c4b0718cc119d86cb6fa855441ff5c606b6dd6f4"
$TorchIndex = "https://download.pytorch.org/whl/cpu"

$env:PIP_CACHE_DIR = Join-Path $Cache "pip"
$env:PIP_DISABLE_PIP_VERSION_CHECK = "1"
$env:PYTHONNOUSERSITE = "1"
Remove-Item Env:PYTHONHOME, Env:PYTHONPATH, Env:VIRTUAL_ENV -ErrorAction SilentlyContinue
$PipInstall = @("-m", "pip", "install", "--no-warn-script-location")

function Step([string]$Message) { Write-Host "==> $Message" -ForegroundColor Cyan }

# Windows PowerShell 5.1 turns every stderr line of a native tool into a
# terminating error under ErrorActionPreference=Stop whenever output is
# redirected (e.g. `build-runtime.ps1 *> build.log`) — and pip writes harmless
# warnings there. So native tools run under "Continue", their output is passed
# through as plain text, and success is judged by exit code alone.
function Invoke-Native {
  param([string]$Exe, [string[]]$Arguments, [switch]$Capture)
  $prev = $ErrorActionPreference
  $ErrorActionPreference = "Continue"
  try {
    if ($Capture) {
      $out = & $Exe @Arguments 2>$null
    } else {
      & $Exe @Arguments 2>&1 | ForEach-Object { Write-Host "$_" }
    }
  } finally {
    $ErrorActionPreference = $prev
  }
  if ($LASTEXITCODE -ne 0) { throw "'$Exe $($Arguments -join ' ')' failed with exit code $LASTEXITCODE" }
  if ($Capture) { return $out }
}

function Copy-Tree([string]$From, [string]$To, [string[]]$ExcludeDirs) {
  $opts = @($From, $To, "/E", "/NFL", "/NDL", "/NJH", "/NJS", "/NP")
  if ($ExcludeDirs) { $opts += "/XD"; $opts += $ExcludeDirs }
  & robocopy @opts | Out-Null
  if ($LASTEXITCODE -ge 8) { throw "robocopy $From -> $To failed ($LASTEXITCODE)" }
  $global:LASTEXITCODE = 0
}

# ── 1. Interpreter ────────────────────────────────────────────────────────────
Step "Python $PyVersion (python-build-standalone $PbsRelease)"
New-Item -ItemType Directory -Force $Cache | Out-Null
$Archive = Join-Path $Cache $PbsFile
if (-not (Test-Path $Archive)) {
  Invoke-WebRequest -UseBasicParsing -Uri $PbsUrl -OutFile "$Archive.part"
  Move-Item "$Archive.part" $Archive
}
$actual = (Get-FileHash -Algorithm SHA256 $Archive).Hash.ToLower()
if ($actual -ne $PbsSha256) {
  Remove-Item $Archive
  throw "SHA-256 mismatch for $PbsFile (got $actual)"
}
if (Test-Path $Runtime) { Remove-Item -Recurse -Force $Runtime }
New-Item -ItemType Directory -Force $Runtime | Out-Null
# The archive's top-level folder is python/ -> build/runtime/python. Windows'
# own bsdtar: a GNU tar earlier on PATH (Git's) reads "C:\..." as host:path.
Invoke-Native (Join-Path $env:SystemRoot "System32\tar.exe") @("-xzf", $Archive, "-C", $Runtime)
Invoke-Native $Py @("-c", "import sys; print(sys.version)")

# ── 2. Dependencies ───────────────────────────────────────────────────────────
if ($RefreshLock -or -not (Test-Path $Lock)) {
  Step "Resolving dependencies from backend/pyproject.toml -> requirements.lock.txt"
  # torch first, from the CPU index, so the [ml] extra is already satisfied by it.
  Invoke-Native $Py ($PipInstall + @("torch", "torchvision", "--index-url", $TorchIndex))
  Invoke-Native $Py ($PipInstall + @("$BackendSrc[ml,desktop]"))
  # The backend itself ships as source (step 3), not as an installed package.
  Invoke-Native $Py @("-m", "pip", "uninstall", "-y", "space-weather-backend")
  $frozen = Invoke-Native $Py @("-m", "pip", "freeze") -Capture
  $header = @(
    "# Pinned dependencies of the desktop app's bundled Python ($PyVersion, win_amd64).",
    "# Generated by desktop/scripts/build-runtime.ps1 -RefreshLock from backend/pyproject.toml",
    "# extras [ml,desktop]. Refresh deliberately; don't hand-edit.",
    "--extra-index-url $TorchIndex"
  )
  [IO.File]::WriteAllLines($Lock, [string[]]($header + $frozen))
} else {
  Step "Installing dependencies from requirements.lock.txt"
  Invoke-Native $Py ($PipInstall + @("-r", $Lock))
}
Invoke-Native $Py @("-m", "pip", "check")

# ── 3. Backend source + checkpoints ───────────────────────────────────────────
Step "Copying backend source and ML checkpoints"
Copy-Tree (Join-Path $BackendSrc "app") (Join-Path $BackendOut "app") @("tests", "__pycache__")
Copy-Tree (Join-Path $BackendSrc "alembic") (Join-Path $BackendOut "alembic") @("__pycache__")
$ModelOut = Join-Path $BackendOut "ml_model"
New-Item -ItemType Directory -Force $ModelOut | Out-Null
foreach ($pt in Get-ChildItem (Join-Path $BackendSrc "ml_model") -Filter *.pt) {
  # An un-pulled Git LFS pointer is a ~130-byte text file, not a model.
  if ($pt.Length -lt 1MB) { throw "$($pt.Name) is a Git LFS pointer - run 'git lfs pull' first" }
  Copy-Item $pt.FullName $ModelOut
}

# ── 4. Trim + byte-compile ────────────────────────────────────────────────────
Step "Trimming build-only files"
# C++ headers and import libraries are only for compiling torch extensions.
$SitePackages = Join-Path $PyDir "Lib\site-packages"
foreach ($rel in @("torch\include", "torch\share")) {
  $p = Join-Path $SitePackages $rel
  if (Test-Path $p) { Remove-Item -Recurse -Force $p }
}
Get-ChildItem (Join-Path $SitePackages "torch\lib") -Filter *.lib -ErrorAction SilentlyContinue | Remove-Item -Force
# Package test suites stay: some packages (astropy) import their tests module at import time.

Step "Byte-compiling (unchecked-hash .pyc)"
# Exit code is non-zero if any single file fails to compile (e.g. deliberately
# broken test fixtures inside packages); those files are simply never imported.
try {
  Invoke-Native $Py @("-m", "compileall", "-q", "-f", "-j", "0", "--invalidation-mode", "unchecked-hash",
    (Join-Path $PyDir "Lib"), $BackendOut) -Capture | Out-Null
} catch {
  Write-Warning "compileall reported files it could not compile (usually harmless test fixtures)"
}
$global:LASTEXITCODE = 0

# ── 5. Smoke test ─────────────────────────────────────────────────────────────
if (-not $SkipSmokeTest) {
  Step "Smoke test: imports and ML checkpoints"
  $env:PYTHONPATH = $BackendOut
  # Written to a file: PS 5.1 mangles multi-line/quoted native arguments.
  $checkPy = Join-Path $BuildDir "smoke_check.py"
  [IO.File]::WriteAllText($checkPy, @"
import torch, sunpy, sunpy.map, astropy, aiapy, drms, reproject, imageio_ffmpeg, aiosqlite, scipy
from app.ml import registry
from app.ml.inference import get_loaded
for spec in registry._SPECS.values():
    assert registry.is_available(spec), f"{spec.id}: checkpoint missing"
    assert get_loaded(spec) is not None, f"{spec.id}: failed to load"
print("torch", torch.__version__, "| sunpy", sunpy.__version__, "| models OK:", ", ".join(registry._SPECS))
"@)
  Invoke-Native $Py @("-P", $checkPy)

  Step "Smoke test: start and stop the desktop backend"
  $SmokeHome = Join-Path $BuildDir "smoke-home"
  if (Test-Path $SmokeHome) { Remove-Item -Recurse -Force $SmokeHome }
  $port = 47899
  $frontend = Join-Path $RepoRoot "frontend\out"
  $psi = New-Object System.Diagnostics.ProcessStartInfo
  $psi.FileName = $Py
  $psi.Arguments = "-P -m app.desktop"
  $psi.UseShellExecute = $false
  $psi.RedirectStandardInput = $true
  $psi.EnvironmentVariables["PYTHONPATH"] = $BackendOut
  $psi.EnvironmentVariables["PYTHONUTF8"] = "1"
  $psi.EnvironmentVariables["SWD_HOME"] = $SmokeHome
  $psi.EnvironmentVariables["SWD_PORT"] = "$port"
  $psi.EnvironmentVariables["SWD_LIFELINE"] = "stdin"
  $psi.EnvironmentVariables["ENABLE_SCHEDULER"] = "false"
  if (Test-Path $frontend) { $psi.EnvironmentVariables["SWD_FRONTEND_DIR"] = $frontend }
  $proc = [System.Diagnostics.Process]::Start($psi)
  try {
    $deadline = (Get-Date).AddSeconds(180)
    $ready = $false
    while (-not $ready -and (Get-Date) -lt $deadline -and -not $proc.HasExited) {
      try {
        $r = Invoke-WebRequest -UseBasicParsing -TimeoutSec 3 "http://127.0.0.1:$port/api/status"
        $ready = $r.StatusCode -eq 200
      } catch { Start-Sleep -Milliseconds 500 }
    }
    if (-not $ready) { throw "desktop backend did not become ready (see $SmokeHome\logs\backend.log)" }
    if (Test-Path $frontend) {
      $page = Invoke-WebRequest -UseBasicParsing -TimeoutSec 10 "http://127.0.0.1:$port/"
      if ($page.StatusCode -ne 200) { throw "UI not served at /" }
    }
    $proc.StandardInput.WriteLine("quit")
    $proc.StandardInput.Close()
    if (-not $proc.WaitForExit(20000)) { throw "backend ignored the quit on its lifeline" }
    if ($proc.ExitCode -ne 0) { throw "backend exited with code $($proc.ExitCode)" }
    Write-Host "    backend started, served /api/status$(if (Test-Path $frontend) {' and /'}), and shut down cleanly"
  } finally {
    if (-not $proc.HasExited) { $proc.Kill() }
    Remove-Item Env:PYTHONPATH -ErrorAction SilentlyContinue
  }
}

$size = (Get-ChildItem -Recurse -File $Runtime | Measure-Object -Sum Length).Sum / 1GB
Step ("Runtime ready: {0} ({1:N2} GB)" -f $Runtime, $size)
