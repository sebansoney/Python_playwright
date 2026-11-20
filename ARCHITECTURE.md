# Architecture - AI-Powered Python Automation Framework (UI + API)

> Status: **complete** (10 phases). This document describes the framework **as built**.
> How-to guides live in [docs/](docs/); progress, verification evidence and known issues in
> [DEVELOPMENT_STATUS.md](DEVELOPMENT_STATUS.md); requirement-by-requirement mapping in
> [docs/requirements_traceability.md](docs/requirements_traceability.md).

---

## 1. Goals

One repository containing (a) a locally runnable **sample application** (FastAPI + SQLite +
server-rendered HTML/JS) and (b) an **automation framework** that tests it at three levels -
UI, API and UI+API integration - with pytest as the runner, Allure for reporting,
pytest-xdist for parallelism, GitHub Actions for CI, and an **optional, advisory AI layer**
(Claude) that never controls execution and never changes code without a human.

---

## 2. Layered view

```
+--------------------------------------------------------------------------+
| tests/ (unit, ui, api, integration, ai_live)            WHAT we verify   |
+--------------------------------------------------------------------------+
| framework/fixtures  (pytest plugins: core, app, execution, api, browser, |
|                      data, reporting, ai)               wiring/lifecycle |
+--------------+------------------+------------------+---------------------+
| UI           | API              | Data             | Assertions          |
| pages/       | api/http_client  | data/factories   | assertions/         |
| components/  | api/auth         | data/backdoor    |  api_assertions     |
| browser/     | api/clients      | data/cleanup     |  schema (JSON Sch.) |
|  session     | api/models       |                  | + Playwright expect |
|              | api/schemas      |                  |                     |
+--------------+------------------+------------------+---------------------+
| core: paths, exceptions, redaction, logging, app_server                  |
| reporting: Allure helpers, run metadata, sanitize  |  utilities          |
+--------------------------------------------------------------------------+
| ai/ (optional, out-of-band): providers <-> AIClient gate <-> services    |
+--------------------------------------------------------------------------+
        | HTTP / browser                                 | HTTPS (only if enabled)
        v                                                v
 sample_application (FastAPI, SQLite)               Claude API
```

**Dependency rule:** downward only. Tests act through pages, clients and fixtures; pages and
clients never assert business outcomes. Nothing outside `framework/ai` depends on AI, and only
`framework/ai/providers/claude.py` imports the vendor SDK.

---

## 3. Folder structure

```
.
├── config/                     config.yaml, environments/{local,ci,staging}.yaml, settings.py
├── framework/
│   ├── core/                   paths, exceptions, redaction, logging_config, app_server
│   ├── browser/session.py      API token <-> browser storage state / cookie
│   ├── pages/                  BasePage + Login/Register, Dashboard, Users(+form),
│   │                           Products(+form, detail), Profile, Tools
│   ├── components/             Form, DataTable, NextDialog, NavBar, FlashMessage
│   ├── api/                    http_client, auth, clients/, models, schemas/*.json
│   ├── assertions/             api_assertions (expect_api), schema
│   ├── data/                   factories (Faker), backdoor (API setup), cleanup registry
│   ├── reporting/              allure_helpers (steps/attachments), run_metadata, sanitize
│   ├── utilities/              waits (non-browser polling), files (CSV)
│   ├── fixtures/               pytest plugins registered by the root conftest.py
│   └── ai/                     providers/, client (gate), factory, evidence, prompts/,
│                               services/, cli
├── tests/                      unit/  ui/  api/  integration/  ai_live/ (opt-in, billed)
├── sample_application/         backend/ (api, web, repository, schemas ...), frontend/,
│                               database/ (runtime, git-ignored), requirements.txt
├── test_data/                  static inputs (images for upload tests)
├── scripts/                    setup, run_app, run_tests, report  (.ps1 + .sh)
├── docs/                       guides, sample report, requirements traceability
├── .github/                    workflows/ci.yml, actions/setup (composite)
├── ai_drafts/  reports/  logs/ generated, git-ignored
└── conftest.py  pyproject.toml  uv.lock  .python-version  .env.example
```

Changes against the original draft structure (agreed in Phase 1): `drivers/` -> `browser/`
(Playwright has no drivers); `framework/test_data/` -> `framework/data/` (code, not files);
no `tests/regression/` (regression is a marker - a selection - not a layer); added
`framework/fixtures/`, `framework/api/schemas/`, `tests/unit/`, `ai_drafts/`; all pytest and
ruff configuration in `pyproject.toml` (no `pytest.ini`).

---

## 4. Technology choices

| Area | Choice | Why |
|---|---|---|
| Language / packaging | Python 3.12, `uv`, `pyproject.toml` + `uv.lock` | One place for dependency ranges; the lock pins exact versions for every machine and CI. |
| UI | Playwright + **pytest-playwright** | Reuse its browser lifecycle, CLI flags and failure artifacts; extend instead of rebuild. |
| API | **HTTPX** (sync) | Independent of browsers; clean hooks for timing, correlation ids and logging. |
| Runner | pytest, pytest-xdist, pytest-rerunfailures | Standard; reruns limited to infrastructure errors. |
| Validation | pydantic v2 (typed models) + jsonschema (contracts) | Typed access in tests + language-neutral contract files. |
| Data | Faker + unique tokens | Realistic, collision-free data - parallel-safe. |
| Config | pydantic-settings + YAML layers | Validated at start-up; env vars / `.env` override YAML. |
| Reporting | allure-pytest + Allure CLI 2.x | Steps, attachments, categories, environment, history. |
| Logging | stdlib `logging` + redacting LogRecord factory | Every record redacted once, whatever handler emits it. |
| Quality | ruff (lint + format) | One fast tool; `time.sleep` banned by rule. |
| Sample app | FastAPI, SQLAlchemy 2, SQLite (WAL, AUTOINCREMENT), Jinja2, PyJWT, bcrypt | Server-rendered, locator-friendly pages; no Node build. |
| AI | Anthropic SDK behind an `LLMProvider` protocol; default `claude-opus-5-5` | Swappable provider; structured outputs; optional and advisory. |
| CI | GitHub Actions | Browser matrix, artifacts, job summary. |

---

## 5. Sample application

Login returns a JWT that the API accepts as `Authorization: Bearer` and the web UI as the
HTTP-only `access_token` cookie - so one login works in both channels (used by integration
tests). Pages: login/logout, register, dashboard, users (admin), products (search, filters,
sort, paging, add/edit/delete, detail in new tab), profile (details, password, avatar upload),
tools (CSV download/upload, iframe, popup, delayed dynamic list). REST API under `/api/v1`
with a uniform error body `{detail, code, correlation_id, errors?}` and `X-Correlation-ID` on
every response. API and web pages share one repository and one set of validation schemas, so
rules and messages cannot drift between UI and API. Full reference:
[docs/sample_application.md](docs/sample_application.md).

---

## 6. Execution flow

```
pytest -m smoke --env local --browser chromium -n 4
 ├─ configure   settings (yaml -> env yaml -> .env -> env vars -> CLI), redaction, logging,
 │              rerun policy, pytest-playwright defaults, Allure results dir (cleaned once)
 ├─ session     app reachable? else ONE worker starts it under a file lock (wait for /health);
 │              API tokens per worker (cached); browser per worker
 ├─ per test    factories create unique data via API (cleanup registered) -> page/context
 │              (optionally logged in via token cookie) -> actions (Allure steps) -> assertions
 │              failure: screenshot, trace, video, DOM snapshot, API exchanges -> Allure
 │              teardown: cleanup runs even after failures
 ├─ finish      environment.properties + categories.json; sanitize pass over all results;
 │              main process stops the app it started
 └─ optional    --ai-analysis: computed run summary (+ AI narrative/failure analysis) -> reports/ai
```

Tests are independent: own data, no ordering, no reliance on leftovers; seed data is
read-only reference data.

---

## 7. AI integration

`framework/ai`: `providers/` (`LLMProvider` protocol, `ClaudeProvider`, `NullProvider`),
`client.py` (the **AIClient gate** every call passes: redaction incl. emails, screenshot policy,
per-run call budget, audit copy of each request, never raises), `factory.py` (any
misconfiguration -> AI off), `evidence.py` (compact local evidence from Allure results; raw
traces never sent), `prompts/` (versioned), `services/` (test cases + manual-to-pytest drafts,
failure analysis, locator suggestions verified on the live page, test data, run summary with
computed grouping) and `cli.py`. Generated code/data can only be written to `ai_drafts/`.
Details: [docs/ai_guide.md](docs/ai_guide.md).

---

## 8. Cross-cutting rules

- **Configuration precedence:** `config.yaml` < `environments/<env>.yaml` < `.env` < env vars < CLI.
- **Waiting:** Playwright auto-waiting and web-first `expect`; `time.sleep` is a lint error;
  non-browser polling uses `utilities/waits.wait_until`.
- **Locators:** role / label first, `data-testid` fallback, CSS last; locators live in page objects.
- **Retries:** infrastructure errors only (local 0, CI 2); `AssertionError` never; reruns visible.
- **Secrets:** one redactor for logs, API exchange renders, Allure steps/attachments, the final
  results sanitize pass and AI requests. Exception: Playwright traces (kept only on failure).
- **Parallel safety:** unique data, per-worker tokens/contexts/logs, SQLite WAL, consistent
  paging queries, ids never reused, one file-locked app server.
- **Markers:** `ui`/`api`/`integration`/`unit` from the folder; every functional test is
  `regression`; `smoke`/`sanity` are subsets; `--strict-markers` catches typos.

---

## 9. Test inventory

| Layer | Tests | Highlights |
|---|---|---|
| UI (`tests/ui`) | 38 | login, registration, user management, products, download/upload, iframe, popup, new tab, dialogs, dynamic content |
| API (`tests/api`) | 96 | CRUD, auth/tokens, negative, boundary, chaining, authorization, contracts, correlation ids, timing |
| Integration (`tests/integration`) | 17 | the five requested cross-layer scenarios + registration, CSV, identical validation, session sharing |
| Framework self-tests (`tests/unit`) | 75 | config, redaction, API layer, reporting, AI gate/services/CLI, rerun policy, markers |
| Live AI (`tests/ai_live`) | 1 | opt-in, real billed call |

UI and integration tests run on Chromium, Firefox and WebKit (55 x 3 per full cross-browser run).

---

## 10. Risks and how they were handled

| Risk | Outcome |
|---|---|
| Flaky parallel runs | Three real app defects found and fixed (id reuse, inconsistent paging, float messages); many repeated `-n 4` runs green. |
| Secrets in artifacts | Layered redaction + sanitize pass + scans of results, reports and AI prompts (0 findings). Traces remain sensitive by nature (documented). |
| AI cost / non-determinism | Advisory only, structured outputs, call budget, effort setting, off by default. |
| SQLite under concurrency | WAL, single-statement paging, AUTOINCREMENT; adequate for a demo app. |
| WebKit on Windows | Green locally; Linux CI is the reference. |
| Windows path limit | Setup warns when the project path is too long (see DEVELOPMENT_STATUS). |

---

## 11. Phases

| Phase | Deliverable | Status |
|---|---|---|
| 1 | Architecture | done |
| 2 | Structure, environment, config, logging, redaction | done |
| 3 | Sample application | done |
| 4 | Playwright UI framework + UI tests | done |
| 5 | HTTPX API framework + API tests | done |
| 6 | UI + API integration tests | done |
| 7 | Allure reporting | done |
| 8 | AI assistance (Claude) | done - live call pending an API key |
| 9 | Parallel execution + GitHub Actions | done - first GitHub run pending a remote |
| 10 | Final regression, fixes, documentation | done |

---

## 12. Decisions log (taken during implementation)

| Phase | Decision | Reason |
|---|---|---|
| 2 | Python installed **inside the project** (`.python/`, via `UV_PYTHON_INSTALL_DIR`) | The Claude desktop app sandboxes `%APPDATA%`; an interpreter there is invisible to your own terminal/IDE. Project-local also means zero impact on any system Python. |
| 2 | All pytest + ruff config in `pyproject.toml`; no `pytest.ini` | Avoid two competing config files. |
| 2 | Config = pydantic-settings; YAML passed as the *lowest*-priority source | Typed + validated at start-up; env vars and `.env` override YAML with deep merge of nested keys. |
| 2 | Test credentials named `FW_CREDENTIALS__*` and **shared with the sample app** | One source for the seeded accounts → framework and app can never disagree. |
| 2 | `ANTHROPIC_API_KEY` keeps its standard name | Works with existing tooling and CI secret conventions. |
| 2 | Redaction applied in a **LogRecord factory** (not a handler filter) | Filters on a logger/handler miss records from child loggers or pytest's capture handler; the factory redacts every record once, at creation. |
| 2 | Added `tests/unit/` (marker `unit`) | Fast self-tests prove config precedence and redaction work before any UI/API test relies on them. |
| 2 | `time.sleep` banned via ruff `TID251` | Enforces "no hard waits" automatically. |
| 3 | Own email regex instead of `email-validator` (dependency removed) | `email-validator` rejects reserved test domains such as `.test`, which we deliberately use for test accounts. |
| 3 | Same pydantic schemas + one message formatter for API and UI | Integration tests can assert identical rules/messages at both layers. |
| 3 | Flash messages via fixed keys (`?flash=product_created`) | No user text is reflected into pages; simple, stateless, testable. |
| 3 | Forms use `novalidate` + server-side validation with inline errors | Native browser validation bubbles are not in the DOM and are browser-specific; inline errors are assertable with normal locators. |
| 3 | Login API also sets the auth cookie | A Playwright `APIRequestContext` sharing the browser's storage is logged in too. |
| 3 | Notification ids are random by design | Teaches (and tests) that locators must not rely on generated ids. |
| 3 | `bcrypt` rounds = 10 | Real hashing but fast enough for many logins in parallel runs. |
| 4 | Build on **pytest-playwright** fixtures (override `browser_context_args`, wrap `new_context`) | Keeps the plugin's browser lifecycle, CLI flags and failure artifacts; we only add config defaults, base URL, timeouts and auth. |
| 4 | Config → pytest-playwright options in `pytest_configure`, unless the flag is on the CLI | `config.yaml` sets team defaults; the CLI still wins for a single run. |
| 4 | App autostart: first worker starts it under a **file lock**; only the run owner (xdist controller) stops it, identified by a run id | Safe with `-n N`: one server, never stopped while workers still need it; a developer's own server is reused and never stopped. |
| 4 | Stop the app by **killing the process tree** | On Windows `.venv\Scripts\python.exe` is a launcher; killing only its PID left the real server running (found during testing). |
| 4 | Browsers installed **inside the project** (`.playwright-browsers/`), used automatically if present | The desktop app sandboxes `%LOCALAPPDATA%`; browsers there are invisible to the user's own terminal. CI keeps Playwright's default location. |
| 4 | Logged-in pages via **storage state** from an API login (`admin_page`, `user_page`, `page_for`) | Login UI is tested once in its own tests; every other test skips it - faster and less flaky. |
| 4 | Test preconditions via API **backdoor** + factories with automatic **cleanup** | Browser time is spent only on the behaviour under test; no leftover data, parallel-safe. |
| 4 | Setup/auth `APIRequestContext`s are created **untraced** | pytest-playwright traces every API context; login traffic put the test password into trace files (found during testing). |
| 4 | Locators in page objects (not separate locator files); role/label first, `data-testid` fallback | Locators sit next to the behaviour that uses them; matches Playwright guidance. |
| 4 | Validation asserted via `aria-invalid` + accessible description | Robust to layout changes and verifies the error is announced to assistive tech. |
| 4 | Required-field `*` moved outside `<label>` in the app; `required` attribute added | `get_by_label("Password", exact=True)` must match the label text exactly. |
| 4 | `BasePage.submit_and_wait` (expect_navigation) for GET-form submits | A URL-based wait passes too early when the URL is unchanged (re-search), so tables could be read before the new page arrived. |
| 5 | App tables use SQLite `AUTOINCREMENT` | Default SQLite rowids reuse the id of a deleted newest row; found via a flaky parallel test, proven by a regression test. |
| 5 | API layer on **HTTPX**: `ApiClient` → resource clients → `ApiSession` per identity | Clear separation: transport concerns (timing, correlation id, logging) once; clients only map endpoints; tests stay declarative. |
| 5 | Clients **never assert**; fluent `expect_api(...)` assertions with the redacted exchange in every failure message | Same client serves positive and negative tests; no repeated validation code; failures explain themselves. |
| 5 | JSON Schema files **and** pydantic models | Schema = shareable contract with `$ref` reuse; pydantic = typed access in tests. |
| 5 | Timestamps checked by explicit ISO-8601 pattern, not `format: date-time` | `format` is silently skipped without an extra package, and the app emits no timezone (N8). |
| 5 | **No cookie persistence** in `ApiClient` (opt-in only) | Found by a probe test: the login `Set-Cookie` silently authenticated an "anonymous" session. |
| 5 | Backdoor and browser storage-state moved onto the HTTPX layer (same public API) | One API layer instead of two; storage state is built from the token (cookie), so no Playwright API contexts and no secrets in traces. |
| 5 | Per-test `api_log` rendered as a report section on failure | Evidence for API failures without re-running (Allure attachment in Phase 7). |
| 6 | List endpoints return items and total from **one statement** (`COUNT(*) OVER ()`) | Two queries saw different snapshots under parallel writes (16 items, `total: 15`); a single statement is always consistent. Wider SQLite transactions were rejected: they risk `database is locked` under concurrent writes. |
| 6 | Session-sharing helpers in `framework/browser/session.py` (`storage_state_for_token`, `token_from_context`) + `page_for_token` fixture | One login usable in both channels, in both directions; used by fixtures and integration tests alike. |
| 6 | Integration tests: setup via backdoor, verification via logged `api` session | Verification steps become failure evidence; setup noise does not. |
| 6 | Ruff does not format Markdown code blocks | Doc examples keep their explanatory layout. |
| 7 | Allure results on **every run** (config default dir); old results cleaned **once by the main process** | allure-pytest's own `--clean-alluredir` runs in every xdist worker and could delete results already written by another worker. |
| 7 | Failure attachments added **after fixture teardown** (`pytest_runtest_teardown` wrapper) | pytest-playwright saves screenshot/trace/video during fixture teardown; the Allure test stays open until `logfinish`, so attachments still land on the test. |
| 7 | Steps via our `step_method` (context-manager steps), never `@allure.step` on methods | `@allure.step` records every argument as a step parameter - a password passed to `login()` would appear in the report. |
| 7 | Final **sanitize pass** over all result JSON at session end | Allure stores test names, parameters and failure messages verbatim; redacting at the source cannot cover them. |
| 7 | Failure **categories** (environment / UI timeout / product defect / test defect) | Readers separate product bugs from environment noise at a glance. |
| 7 | `core.bootstrap()` made idempotent | Plugins that need settings in `pytest_configure` call it instead of depending on hook order. |
| 7 | Report scripts copy previous `history/` | Allure trends need history carried across runs. |
| 8 | Default model **`claude-opus-5-5`** (Phase 1 proposed a Sonnet-class default) | Most capable Opus per current Anthropic guidance; cost is a user decision - one config line switches to Sonnet/Haiku, and effort + call budget bound spend. |
| 8 | Single **AIClient gate** for every call (redact incl. emails, image policy, budget, audit file, never raises) | Safety rules cannot be bypassed by a new service; AI problems can never break a run. |
| 8 | Structured outputs (pydantic) for every assistant | Typed, validated answers; reports and drafts are built by code, not by parsing prose. |
| 8 | Evidence extracted locally from Allure results; raw traces never sent | Small, relevant, redacted context; cookies/typed values in traces stay local. |
| 8 | Redacted **DOM snapshot** attached to failed UI tests (as text) | Humans and the locator assistant see the page at failure; text avoids executing HTML inside the report. |
| 8 | Locator candidates are structured (strategy + value) and verified by match count | No `eval` of model output; ambiguous/invalid suggestions are flagged, not trusted. |
| 8 | Drafts only in `ai_drafts/`; `write_draft` refuses `tests/`, `framework/`, `config/` | Human approval is enforced in code. |
| 8 | Run grouping / recurring / flaky detection computed without AI | Deterministic and free; AI only adds the narrative. |
| 9 | Rerun patterns are bare exception class names (`^ConnectError: `) + `AssertionError` always excluded in code | pytest-rerunfailures matches `"<ClassName>: <msg>"` without module: the Phase 2 patterns (`httpx.ConnectError`) could never match. Exclusion also stops assertions raised while handling an infra error. |
| 9 | Reruns off locally, 2 in CI | Developers see flakiness immediately; CI absorbs runner hiccups; reruns always visible. |
| 9 | CI uses the framework's app autostart (Phase 1 planned an explicit start step) | Proven xdist-safe; one code path locally and in CI; simpler workflow. |
| 9 | Random per-run test-account passwords in CI (no repository secrets) | Nothing hard-coded or published; works for forks/PRs; the app seeds from the same variables. |
| 9 | Jobs: quality → api + ui×3 browsers → report (merge results, single-file Allure, job summary) | Fast feedback first; browsers in parallel; one combined report artifact. |
| 9 | Actions pinned to verified current majors; `setup-uv` to an exact version | Avoid retired Node runtimes; setup-uv has no moving major tag. |
| 10 | `regression` auto-applied to every ui/api/integration test; smoke and sanity are subsets | `-m regression` previously selected 121 of 151 functional tests and skipped every smoke/sanity test. |
| 10 | Setup script warns about long project paths on Windows; AI factory reports the real import error | A clean-copy check in a deep folder broke the `anthropic` import (260-char path limit); the old message wrongly said "not installed". |
