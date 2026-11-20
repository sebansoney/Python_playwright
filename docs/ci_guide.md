# Parallel Execution & CI/CD Guide

## Parallel execution (pytest-xdist)

```bash
uv run pytest -n 4                     # 4 worker processes
uv run pytest -n auto                  # one per CPU core
uv run pytest -n 4 --browser chromium --browser firefox --browser webkit
```
Why it is safe:
- **One app server** per run: the first worker that needs it starts it under a file lock;
  the main process stops it at the end. An app you started yourself is reused, never stopped.
- **Independent data**: every test creates unique records (factories) and cleans up;
  list assertions check properties, not shared totals.
- **Per-worker** login tokens, browser contexts and log files (`logs/run_gw0.log`, ...).
- **Allure results** from all workers land in one folder (cleaned once, by the main process).
- Verified repeatedly: 12 consecutive `-n 4` runs of the whole suite green (DEVELOPMENT_STATUS).

Preset runner (same on Windows / Linux):
```powershell
powershell -File scripts\run_tests.ps1 -Suite regression -Browsers chromium,firefox,webkit -Report
```
```bash
bash scripts/run_tests.sh api --workers 8 --report
```
Suites: `smoke`, `sanity`, `regression`, `unit`, `api`, `ui`, `integration`, `full`.

## Retries - infrastructure only

Configured in `config/*.yaml` → `retry:`; applied by `framework/fixtures/execution.py`.

| Environment | Reruns | Why |
|---|---|---|
| `local` | 0 | see every flaky failure immediately |
| `ci` | up to 2, 2 s apart | shared runners have rare network/browser hiccups |

- A failure is rerun **only** if `"<ExceptionClass>: <message>"` matches one of
  `retry.only_rerun` (connection refused/timeout, dropped connection, browser closed/crashed).
- **`AssertionError` is never rerun** - including Playwright `expect` failures and assertions
  raised while handling a connection error. This is enforced in code, not config.
- Reruns stay visible: `R` in the terminal, `N rerun` in the summary, the Allure *Retries* tab.
- One-off override: `pytest --reruns 0` (or any number - assertions are still never rerun).
- The header of every run says what is active, e.g.
  `reruns: up to 2x, only for: ^ConnectError: , ...; never for AssertionError`.

## GitHub Actions (`.github/workflows/ci.yml`)

```
push / PR / nightly 02:00 UTC / manual
        │
     quality ── ruff lint + format check + 70 framework self-tests
      │    │
     api   ui (matrix: chromium | firefox | webkit) ── UI + integration, -n 4
      │    │
      report ── merge all Allure results → single-file Allure report + job summary
                (+ AI failure analysis when enabled)
```

| Job | Runs | Artifacts |
|---|---|---|
| `quality` | `ruff check`, `ruff format --check`, `pytest -m unit -n auto` | `allure-results-unit` |
| `api` | `pytest tests/api -n 4` | `allure-results-api`, logs on failure |
| `ui` ×3 | `pytest tests/ui tests/integration -n 4 --browser <b>` | `allure-results-<b>`, screenshots/traces/videos + logs on failure |
| `report` | merge → `allure generate --single-file` → summary | `allure-report` (open `index.html`), `ai-analysis` |

Details:
- **No secrets required.** `.github/actions/setup` generates **random test-account passwords**
  per run (masked in logs). The sample app seeds itself from them; nothing is hard-coded.
- `TEST_ENV=ci` → `config/environments/ci.yaml`: headless, video on failure, app autostart,
  infrastructure-only reruns.
- Dependencies install from `uv.lock` (`uv sync --locked`); Python 3.12 from `.python-version`.
- The run page shows a results table and the computed run summary (job summary).
- Pinned actions (verified Nov 2026, all Node 24): `actions/checkout@v7`,
  `actions/upload-artifact@v7`, `actions/download-artifact@v8`, `astral-sh/setup-uv@v10.3.3`
  (setup-uv publishes no moving `v10` tag). Allure CLI 2.41.0 from Maven Central.
- `concurrency` cancels superseded runs of the same branch; every job has a timeout.

### Optional: AI analysis in CI
1. Repository **secret** `ANTHROPIC_API_KEY`.
2. Either run the workflow manually with *ai_analysis* ticked, or set the repository
   **variable** `AI_ANALYSIS=true` for every run.
Without the secret the report job still produces the computed summary.

### Not (yet) included
- Publishing the report to GitHub Pages with trend history (needs Pages enabled and write
  permissions; can be added as a separate job).
- Caching Playwright browsers between runs (each run installs one browser, ~1 min).

## Local CI simulation (how the workflow was verified)
The jobs' exact commands were run locally with `TEST_ENV=ci` and random credentials, results
kept per job and merged like the artifacts, then the report job's scripts, the single-file
Allure build and the job summary were executed - see DEVELOPMENT_STATUS (Phase 9).
