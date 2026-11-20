#!/usr/bin/env bash
# Run a test suite with sensible defaults, then (optionally) build the Allure report.
#
# Usage:  bash scripts/run_tests.sh [suite] [--browsers chromium,firefox] [--workers N|auto|0]
#                                   [--env ci] [--headed] [--report] [--ai-analysis]
# Suites: smoke (default) | sanity | regression | unit | api | ui | integration | full
set -uo pipefail
cd "$(dirname "$0")/.."

SUITE="smoke"; BROWSERS="chromium"; WORKERS="4"; EXTRA=(); REPORT=0
if [[ $# -gt 0 && "$1" != --* ]]; then SUITE="$1"; shift; fi
while [[ $# -gt 0 ]]; do
  case "$1" in
    --browsers) BROWSERS="$2"; shift 2 ;;
    --workers) WORKERS="$2"; shift 2 ;;
    --env) EXTRA+=(--env "$2"); shift 2 ;;
    --headed) EXTRA+=(--headed); shift ;;
    --ai-analysis) EXTRA+=(--ai-analysis); shift ;;
    --report) REPORT=1; shift ;;
    *) echo "unknown option: $1"; exit 2 ;;
  esac
done

case "$SUITE" in
  smoke) SEL=(-m smoke) ;;
  sanity) SEL=(-m sanity) ;;
  regression) SEL=(-m regression) ;;
  unit) SEL=(-m unit) ;;
  api) SEL=(tests/api) ;;
  ui) SEL=(tests/ui) ;;
  integration) SEL=(tests/integration) ;;
  full) SEL=(tests/unit tests/api tests/ui tests/integration) ;;
  *) echo "unknown suite: $SUITE"; exit 2 ;;
esac

ARGS=("${SEL[@]}")
[[ "$WORKERS" != "0" ]] && ARGS+=(-n "$WORKERS")
IFS=',' read -ra BLIST <<< "$BROWSERS"
for b in "${BLIST[@]}"; do ARGS+=(--browser "$b"); done
ARGS+=("${EXTRA[@]}")

echo "uv run pytest ${ARGS[*]}"
uv run pytest "${ARGS[@]}"
CODE=$?
[[ "$REPORT" == 1 ]] && bash scripts/report.sh --open
exit $CODE
