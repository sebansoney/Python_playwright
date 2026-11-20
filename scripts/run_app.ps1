# Start the sample application in the foreground.
# Usage:  powershell -File scripts\run_app.ps1 [-Port 8000] [-Env test] [-ResetDb] [-Reload]
param([int]$Port = 8000, [string]$Env = "test", [switch]$ResetDb, [switch]$Reload)
Set-Location (Split-Path $PSScriptRoot -Parent)
$extra = @()
if ($ResetDb) { $extra += "--reset-db" }
if ($Reload) { $extra += "--reload" }
uv run python -m sample_application --port $Port --env $Env @extra
