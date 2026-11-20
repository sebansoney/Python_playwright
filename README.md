# AI-Powered Python Automation Framework (UI + API)

Playwright + pytest framework for **UI, REST API and UI+API integration** testing, with
Allure reporting, parallel execution, GitHub Actions CI and an optional, advisory AI layer
(Claude). It ships with a locally runnable sample application (FastAPI + SQLite) used as the
system under test.

| | |
|---|---|
| Tests | 38 UI · 96 API · 17 integration · 75 framework self-tests (+1 opt-in live AI test) |
| Browsers | Chromium, Firefox, WebKit |
| Status | All 10 phases complete - see [DEVELOPMENT_STATUS.md](DEVELOPMENT_STATUS.md) |
| Design | [ARCHITECTURE.md](ARCHITECTURE.md) · [Requirements traceability](docs/requirements_traceability.md) |
| Guides | [UI](docs/ui_testing_guide.md) · [API](docs/api_testing_guide.md) · [Integration](docs/integration_testing_guide.md) · [Reporting](docs/reporting_guide.md) · [AI](docs/ai_guide.md) · [CI](docs/ci_guide.md) · [Sample app](docs/sample_application.md) |
| Sample report | [docs/sample-report/index.html](docs/sample-report/index.html) (single file - open in a browser) |

---

## 1. Prerequisites

| Tool | Needed for | Install |
|---|---|---|
| [uv](https://docs.astral.sh/uv/) | Python 3.12 + all dependencies | Windows: `winget install --id astral-sh.uv -e` · macOS/Linux: see uv docs |
| Git | cloning, CI | - |
| Java 8+ and [Allure CLI 2.x](https://allurereport.org/docs/install/) | *optional*: viewing the HTML report locally | - |

You do **not** need a system Python: `uv` installs Python 3.12 inside the project (`.python/`).

> **Windows:** keep the project path short (≤ 90 characters, e.g. `C:\work\automation`) unless
> Windows long paths are enabled - some dependency files are nested deeply. The setup script warns you.

## 2. Install

Windows PowerShell:
```powershell
powershell -ExecutionPolicy Bypass -File scripts\setup.ps1
```
Linux / macOS / Git Bash:
```bash
bash scripts/setup.sh
```
The script installs Python, creates `.venv`, installs the locked dependencies (`uv.lock`),
creates `.env` from `.env.example`, installs the Playwright browsers (Chromium, Firefox,
WebKit) and runs the framework self-tests. Add `-SkipBrowsers` / `--skip-browsers` to skip the
~600 MB browser download.

`.env` holds the **test accounts** for the local sample app (`FW_CREDENTIALS__*`) and, optionally,
`ANTHROPIC_API_KEY`. It is git-ignored - never commit it.

## 3. Run tests

```bash
uv run pytest                                   # everything (Chromium)
uv run pytest -m smoke                          # critical paths
uv run pytest -m regression --browser chromium  # full functional suite
uv run pytest tests/ui                          # by layer: tests/ui | tests/api | tests/integration
uv run pytest -n 4                              # parallel (pytest-xdist); -n auto = one per CPU
uv run pytest -n 4 --browser chromium --browser firefox --browser webkit
uv run pytest tests/ui --headed --slowmo 300    # watch the browser
uv run pytest --env ci                          # config/environments/ci.yaml
uv run pytest -m unit                           # framework self-tests (no app, no browser)
```
The sample app is **started automatically** when a test needs it and stopped afterwards.
Markers: `smoke` and `sanity` are subsets of `regression` (= every UI/API/integration test);
`ui`, `api`, `integration`, `unit` are applied from the folder.

Presets (same on every OS):
```powershell
powershell -File scripts\run_tests.ps1 -Suite regression -Browsers chromium,firefox,webkit -Report
```
```bash
bash scripts/run_tests.sh api --workers 8 --report
```
Suites: `smoke`, `sanity`, `regression`, `unit`, `api`, `ui`, `integration`, `full`.

## 4. Reports

Every run writes Allure results to `reports/allure-results`. Build and open the report:
```powershell
powershell -File scripts\report.ps1 -Open
```
```bash
bash scripts/report.sh --open
```
Add `-SingleFile` / `--single-file` for one shareable `index.html`. Failed UI tests carry a
screenshot, Playwright trace and DOM snapshot; failed API tests the redacted request/response.
Trends build up across runs. Details: [docs/reporting_guide.md](docs/reporting_guide.md).

## 5. Sample application (run it yourself)

```bash
uv run python -m sample_application --env test --reset-db    # http://127.0.0.1:8000
```
Log in with the accounts from `.env`. API docs: <http://127.0.0.1:8000/docs>.
Reference (endpoints, rules, test hooks): [docs/sample_application.md](docs/sample_application.md).

## 6. AI assistance (optional)

Put `ANTHROPIC_API_KEY=...` and `FW_AI__ENABLED=true` in `.env`, then:
```bash
uv run python -m framework.ai status
```
```bash
uv run pytest --ai-analysis
```
Failure analysis, run summary, test-case and test-data generation, locator suggestions.
Advisory only: everything is redacted before sending, generated code goes to `ai_drafts/` for
human review, and the framework works identically without AI. Default model `claude-opus-5-5`
(switch with `FW_AI__MODEL`). Details: [docs/ai_guide.md](docs/ai_guide.md).

## 7. CI/CD

`.github/workflows/ci.yml`: lint + self-tests → API and UI (Chromium, Firefox, WebKit) in
parallel → one merged Allure report (artifact) + job summary. No repository secrets needed
(random per-run test passwords); infrastructure-only reruns (never for assertions); optional
AI analysis with an `ANTHROPIC_API_KEY` secret. Details: [docs/ci_guide.md](docs/ci_guide.md).

## 8. Configuration

Precedence (lowest → highest): `config/config.yaml` → `config/environments/<env>.yaml` →
`.env` → environment variables → pytest CLI options.

* Environment variables use the prefix `FW_` and `__` for nesting: `FW_BROWSER__HEADLESS=false`,
  `FW_API__TIMEOUT_S=5`, `FW_AI__ENABLED=true`.
* Environment: `--env <name>` or `TEST_ENV` (default `local`).
* Secrets live only in `.env` / CI secrets - never in YAML. Unknown keys or invalid values stop
  the run with a clear message.

## 9. Code quality

```bash
uv run ruff check .
```
```bash
uv run ruff format .
```
`time.sleep` is a lint error - use Playwright auto-waiting or `framework.utilities.waits`.

## 10. Troubleshooting

| Symptom | Fix |
|---|---|
| `uv` not found right after installing it | Open a new terminal (PATH is updated for new shells only). |
| `Credentials for 'admin' are not configured` | Create `.env` from `.env.example` (the setup script does this). |
| `Application not reachable ... autostart is disabled` | You use an env with `app.autostart: false` - start the app yourself (section 5). |
| Port 8000 already in use by something else | Stop that process, or set `app.base_url` (e.g. `FW_APP__BASE_URL=http://127.0.0.1:8001`). |
| Playwright says the browser executable is missing | `uv run playwright install chromium firefox webkit` (or rerun the setup script). |
| AI says `'anthropic' SDK could not be imported` on Windows | Project path too long - move it to a shorter folder or enable Windows long paths. |
| Report script: `Allure CLI not found` | Install Java 8+ and the Allure CLI, or use the CI report artifact. |
| A test fails only in parallel | Check it creates its own data (factories) and does not rely on list totals - see [docs/ui_testing_guide.md](docs/ui_testing_guide.md). |
