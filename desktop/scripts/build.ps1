<#
.SYNOPSIS
  Builds the Windows installer: desktop/dist/SolarMonitoringDashboard-Setup-<version>.exe

.DESCRIPTION
  1. build-runtime.ps1 — bundled Python + backend + ML checkpoints (desktop/build/runtime)
  2. frontend `npm run build:desktop` — static UI export (frontend/out)
  3. electron-builder — Electron shell + NSIS installer (desktop/dist)

  Needs Node 20+, Git LFS checkpoints pulled (`git lfs pull`), and network access
  on the first run (Python, PyTorch CPU and the scientific stack are cached in
  desktop/build/cache afterwards). Don't run it while `next dev` serves from
  frontend/ on this machine: `next build` rewrites frontend/.next.

.PARAMETER SkipRuntime
  Reuse desktop/build/runtime from a previous build (UI/shell-only changes).

.PARAMETER Publish
  Upload the installer + latest.yml to a draft GitHub release v<version>
  instead of only building locally. Needs GH_TOKEN. CI normally does this.
#>
param(
  [switch]$SkipRuntime,
  [switch]$Publish
)

$ErrorActionPreference = "Stop"
$DesktopDir = Split-Path -Parent $PSScriptRoot
$RepoRoot = Split-Path -Parent $DesktopDir
$FrontendDir = Join-Path $RepoRoot "frontend"

function Step([string]$Message) { Write-Host "==> $Message" -ForegroundColor Cyan }

# See build-runtime.ps1: judge native tools by exit code, not by stderr output.
function Invoke-Native {
  param([string]$Exe, [string[]]$Arguments, [string]$WorkDir)
  $prev = $ErrorActionPreference
  $ErrorActionPreference = "Continue"
  Push-Location $WorkDir
  try {
    & $Exe @Arguments 2>&1 | ForEach-Object { Write-Host "$_" }
  } finally {
    Pop-Location
    $ErrorActionPreference = $prev
  }
  if ($LASTEXITCODE -ne 0) { throw "'$Exe $($Arguments -join ' ')' failed with exit code $LASTEXITCODE" }
}

if ($SkipRuntime) {
  if (-not (Test-Path (Join-Path $DesktopDir "build\runtime\python\python.exe"))) {
    throw "No staged runtime in desktop/build/runtime - run without -SkipRuntime first."
  }
} else {
  & (Join-Path $PSScriptRoot "build-runtime.ps1")
}

Step "Frontend static export (frontend/out)"
if (-not (Test-Path (Join-Path $FrontendDir "node_modules"))) { Invoke-Native "npm" @("ci") $FrontendDir }
Invoke-Native "npm" @("run", "build:desktop") $FrontendDir

Step "Electron shell + installer"
if (-not (Test-Path (Join-Path $DesktopDir "node_modules"))) { Invoke-Native "npm" @("ci") $DesktopDir }
$target = if ($Publish) { "release" } else { "dist" }
Invoke-Native "npm" @("run", $target) $DesktopDir

$installer = Get-ChildItem (Join-Path $DesktopDir "dist") -Filter "*.exe" |
  Sort-Object LastWriteTime -Descending | Select-Object -First 1
Step ("Installer: {0} ({1:N0} MB)" -f $installer.FullName, ($installer.Length / 1MB))
