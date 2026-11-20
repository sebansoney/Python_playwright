#!/usr/bin/env bash
# One-time developer setup (Linux / macOS / Git Bash).
# Usage:  bash scripts/setup.sh [--skip-browsers]
set -euo pipefail
cd "$(dirname "$0")/.."

command -v uv >/dev/null || { echo "uv not found: https://docs.astral.sh/uv/getting-started/installation/"; exit 1; }

# Python lives inside the project (.python/) so every shell/IDE sees the same interpreter.
export UV_PYTHON_INSTALL_DIR="$PWD/.python"
uv python install 3.12 --no-bin
[ -d .venv ] || uv venv .venv --python 3.12 --managed-python
uv sync

[ -f .env ] || { cp .env.example .env; echo "Created .env from .env.example - review it."; }

# Browsers also live inside the project (the framework finds them automatically).
export PLAYWRIGHT_BROWSERS_PATH="$PWD/.playwright-browsers"
if [ "${1:-}" != "--skip-browsers" ]; then
  if [ "$(uname -s)" = "Linux" ]; then uv run playwright install --with-deps chromium firefox webkit
  else uv run playwright install chromium firefox webkit; fi
fi

uv run pytest -m unit -q
