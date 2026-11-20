# Run a test suite with sensible defaults, then (optionally) build the Allure report.
#
# Usage:
#   powershell -File scripts\run_tests.ps1                         # smoke, chromium, 4 workers
#   powershell -File scripts\run_tests.ps1 -Suite regression -Browsers chromium,firefox,webkit
#   powershell -File scripts\run_tests.ps1 -Suite api -Workers 8 -Report
#   powershell -File scripts\run_tests.ps1 -Suite full -Env ci -AiAnalysis
#
# Suites: smoke | sanity | regression | unit | api | ui | integration | full
param(
    [ValidateSet("smoke", "sanity", "regression", "unit", "api", "ui", "integration", "full")]
    [string]$Suite = "smoke",
    [string[]]$Browsers = @("chromium"),
    [string]$Workers = "4",          # number or "auto"; "0" = no parallelism
    [string]$Env = "",               # config environment (default: TEST_ENV / local)
    [switch]$Headed,
    [switch]$Report,                 # build + open the Allure report afterwards
    [switch]$AiAnalysis              # AI failure analysis + run summary (needs key)
)
Set-Location (Split-Path $PSScriptRoot -Parent)

$selection = switch ($Suite) {
    "smoke"       { @("-m", "smoke") }
    "sanity"      { @("-m", "sanity") }
    "regression"  { @("-m", "regression") }
    "unit"        { @("-m", "unit") }
    "api"         { @("tests/api") }
    "ui"          { @("tests/ui") }
    "integration" { @("tests/integration") }
    "full"        { @("tests/unit", "tests/api", "tests/ui", "tests/integration") }
}

$pytestArgs = @($selection)
if ($Workers -ne "0") { $pytestArgs += @("-n", $Workers) }
foreach ($b in ($Browsers -join ",").Split(",")) { if ($b) { $pytestArgs += @("--browser", $b.Trim()) } }
if ($Env) { $pytestArgs += @("--env", $Env) }
if ($Headed) { $pytestArgs += "--headed" }
if ($AiAnalysis) { $pytestArgs += "--ai-analysis" }

Write-Host "uv run pytest $($pytestArgs -join ' ')" -ForegroundColor Cyan
uv run pytest @pytestArgs
$code = $LASTEXITCODE

if ($Report) { powershell -ExecutionPolicy Bypass -File scripts\report.ps1 -Open }
exit $code
