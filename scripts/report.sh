#!/usr/bin/env bash
# Build (and optionally open) the Allure HTML report from the last test run.
# Keeps trend history between runs by copying the previous report's history first.
#
# Usage:  bash scripts/report.sh [--open] [--single-file]
set -euo pipefail
cd "$(dirname "$0")/.."

RESULTS="reports/allure-results"
REPORT="reports/allure-report"
OPEN=0; SINGLE=()
for arg in "$@"; do
  case "$arg" in
    --open) OPEN=1 ;;
    --single-file) SINGLE=(--single-file) ;;
    *) echo "unknown option: $arg"; exit 2 ;;
  esac
done

command -v allure >/dev/null || { echo "Allure CLI not found (needs Java 8+): https://allurereport.org/docs/install/"; exit 1; }
[ -d "$RESULTS" ] || { echo "No results in $RESULTS - run the tests first (uv run pytest)."; exit 1; }

[ -d "$REPORT/history" ] && cp -r "$REPORT/history" "$RESULTS/history"

allure generate "$RESULTS" -o "$REPORT" --clean "${SINGLE[@]}"
echo "Report: $REPORT/index.html"
if [ "$OPEN" = 1 ]; then allure open "$REPORT"; fi
