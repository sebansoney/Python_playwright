# Build (and optionally open) the Allure HTML report from the last test run.
# Keeps trend history between runs by copying the previous report's history first.
#
# Usage:
#   powershell -File scripts\report.ps1              # generate reports\allure-report
#   powershell -File scripts\report.ps1 -Open        # generate + open in the browser
#   powershell -File scripts\report.ps1 -SingleFile  # one self-contained index.html (easy to share)
param([switch]$Open, [switch]$SingleFile)
$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)

$results = "reports\allure-results"
$report = "reports\allure-report"

if (-not (Get-Command allure -ErrorAction SilentlyContinue)) {
    Write-Host "Allure CLI not found. Install it (needs Java 8+): https://allurereport.org/docs/install/" -ForegroundColor Yellow
    exit 1
}
if (-not (Test-Path $results)) {
    Write-Host "No results in $results - run the tests first (uv run pytest)." -ForegroundColor Yellow
    exit 1
}

# Trend history: previous report -> new results
if (Test-Path "$report\history") {
    Copy-Item "$report\history" "$results\history" -Recurse -Force
}

$generateArgs = @("generate", $results, "-o", $report, "--clean")
if ($SingleFile) { $generateArgs += "--single-file" }
allure @generateArgs
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Write-Host "Report: $report\index.html" -ForegroundColor Green

if ($Open) {
    if ($SingleFile) { Start-Process "$report\index.html" } else { allure open $report }
}
