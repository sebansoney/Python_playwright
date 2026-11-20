# One-time developer setup (Windows PowerShell).
# Usage:  powershell -ExecutionPolicy Bypass -File scripts\setup.ps1 [-SkipBrowsers]
param([switch]$SkipBrowsers)
$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)

# Windows 260-character path limit: some dependency files sit ~165 chars below the project
# root, so a deeply nested project folder breaks imports unless long paths are enabled.
$root = (Get-Location).Path
$longPaths = (Get-ItemProperty "HKLM:\SYSTEM\CurrentControlSet\Control\FileSystem" -Name LongPathsEnabled -ErrorAction SilentlyContinue).LongPathsEnabled
if ($root.Length -gt 90 -and $longPaths -ne 1) {
    Write-Host "WARNING: project path is $($root.Length) characters long and Windows long paths are disabled." -ForegroundColor Yellow
    Write-Host "         Some packages (e.g. the anthropic SDK) may fail to import. Move the project to a shorter" -ForegroundColor Yellow
    Write-Host "         path (<= 90 chars, e.g. C:\work\automation) or ask an administrator to enable long paths." -ForegroundColor Yellow
}

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Host "uv not found. Install it with:  winget install --id astral-sh.uv -e" -ForegroundColor Yellow
    exit 1
}

# Python lives inside the project (.python/) so every shell/IDE sees the same interpreter.
$env:UV_PYTHON_INSTALL_DIR = Join-Path (Get-Location) ".python"
uv python install 3.12 --no-bin
if (-not (Test-Path .venv)) { uv venv .venv --python 3.12 --managed-python }
uv sync

if (-not (Test-Path .env)) {
    Copy-Item .env.example .env
    Write-Host "Created .env from .env.example - review it." -ForegroundColor Cyan
}

# Browsers also live inside the project (the framework finds them automatically).
$env:PLAYWRIGHT_BROWSERS_PATH = Join-Path (Get-Location) ".playwright-browsers"
if (-not $SkipBrowsers) { uv run playwright install chromium firefox webkit }

uv run pytest -m unit -q
