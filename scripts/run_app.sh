#!/usr/bin/env bash
# Start the sample application in the foreground.
# Usage:  bash scripts/run_app.sh [--port 8000] [--env test] [--reset-db] [--reload]
set -euo pipefail
cd "$(dirname "$0")/.."
exec uv run python -m sample_application --env test "$@"
