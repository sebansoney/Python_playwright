# Requirements Traceability

Every requirement of the original project brief, where it is implemented, and the evidence
that it works. Section numbers follow the brief. Status: ✅ done and verified ·
⚠️ done, but needs your action to verify fully.

## 2. Objectives

| # | Objective | Implementation | Evidence |
|---|---|---|---|
| 1 | Web UI automation | `framework/pages`, `components`, `fixtures/browser.py` | 38 UI tests × 3 browsers |
| 2 | REST API automation | `framework/api`, `assertions` | 96 API tests |
| 3 | End-to-end UI + API | `tests/integration`, `browser/session.py` | 17 integration tests × 3 browsers |
| 4 | Data-driven testing | `pytest.mark.parametrize` (e.g. `test_price_boundaries`, `test_registration_validation`), Faker factories, AI data generator | parametrized tests in `tests/api`, `tests/ui` |
| 5 | Reusable utilities/components | `components/`, `data/`, `utilities/`, `assertions/` | used across all layers |
| 6 | AI test case generation | `ai/services/test_cases.py`, CLI `generate-tests`, `convert-manual` | `tests/unit/test_ai_services.py` ⚠️ live |
| 7 | AI failure analysis | `ai/services/failures.py`, `pytest --ai-analysis` | unit tests + real-failure evidence/prompt scan ⚠️ live |
| 8 | Automated reporting | Allure plugin `fixtures/reporting.py`, `scripts/report.*` | `docs/sample-report/index.html` |
| 9 | Parallel execution | pytest-xdist, file-locked app autostart | repeated `-n 4` cross-browser runs green |
| 10 | CI/CD integration | `.github/workflows/ci.yml` | local CI simulation green ⚠️ first GitHub run |

## 3. Technology stack

Python 3.12 ✅ · Playwright ✅ · pytest ✅ · Playwright browser automation ✅ · HTTPX for API ✅
(APIRequestContext replaced in Phase 5) · POM ✅ · Allure ✅ · pydantic + JSON Schema ✅ ·
Faker ✅ · SQLite ✅ · logging ✅ · Ruff ✅ · GitHub Actions ✅ · Claude API ✅ (⚠️ live) ·
central dependency file `pyproject.toml` + `uv.lock` ✅

## 4. Sample application

| Feature | Where | Tested by |
|---|---|---|
| Login / logout | `web/auth_pages.py`, `api/auth.py` | `tests/ui/test_login.py`, `tests/api/test_auth_api.py` |
| Registration | same | `tests/ui/test_registration.py`, `test_register_then_login_with_new_account` |
| Dashboard | `web/dashboard_pages.py` | `test_valid_login_opens_dashboard`, session tests |
| User management | `web/user_pages.py`, `api/users.py` | `tests/ui/test_user_management.py`, `tests/api/test_users_api.py` |
| Product listing, search, filters | `web/product_pages.py`, `api/products.py` | `tests/ui/test_products.py`, `tests/api/test_products_api.py` |
| Add / update / delete | same | UI + API CRUD tests, integration tests |
| Form validations | `schemas.py`, `validation.py` | validation tests in UI/API + `test_validation_rules_are_identical_in_ui_and_api` |
| Profile management | `web/profile_pages.py`, `api/profile.py` | avatar tests, `test_profile_password_change_flow`, `test_profile_change_in_ui_is_visible_via_api` |
| REST endpoints for the same functions | `backend/api/` | 96 API tests |
| Runs locally, no external sites | FastAPI + SQLite, autostart | every run |

## 5. Architecture
Structure as proposed, with the agreed improvements (ARCHITECTURE.md §3). ✅

## 6. UI automation

| Requirement | Implementation | Evidence |
|---|---|---|
| Browser management & lifecycle | pytest-playwright + `fixtures/browser.py` | all UI tests |
| Chromium, Firefox, WebKit | `--browser`, config default | 3-browser runs |
| Headless / headed | `browser.headless`, `--headed` | config + CLI |
| Page Object Model, reusable actions | `framework/pages`, `components` | all UI tests |
| Locator management | role/label/test-id in page objects | `docs/ui_testing_guide.md` |
| Auto-waiting, no hard waits | `expect`, `submit_and_wait`; `time.sleep` lint error | ruff TID251 |
| Screenshot on failure | `browser.screenshot: only-on-failure` + Allure attach | sample report |
| Video / trace when configured | `browser.video`, `browser.trace`, CLI flags | Phase 4/7 probes |
| Download & upload + validation | `ToolsPage.export_products/import_products`, `ProfilePage.upload_avatar` | `test_export_products_downloads_valid_csv`, import + avatar tests |
| Dropdown | `Form.select` | product/user forms, filters |
| Table | `DataTable` | users/products tests |
| iframe | `ToolsPage.help_frame` | `test_help_iframe_contact_form` |
| Popup / multiple tabs | `expect_popup` | `test_help_opens_in_popup_window`, `test_view_product_opens_in_new_tab` |
| JS dialogs | `NextDialog` | delete / cancel-delete tests |
| Dynamic elements | delayed notifications, random ids | `test_notifications_load_dynamically` |
| Authentication & session management | `admin_page`, `user_page`, `page_for`, `page_for_token` | session-sharing tests |
| Cross-browser execution | browser matrix | 336-test runs |

## 7. API automation

| Requirement | Implementation | Evidence |
|---|---|---|
| GET/POST/PUT/PATCH/DELETE | `ApiClient`, resource clients | CRUD tests |
| Base URL / environment config | `config/*.yaml`, `--env` | `--env ci` runs |
| Auth & token management | `TokenProvider`, `BearerAuth`, `StaticBearerAuth` | auth tests |
| Headers & query params | client kwargs, `products.list(**filters)` | filter / header tests |
| Payload management | factories, `to_api()`, raw dicts for negative cases | invalid-payload tests |
| Status / body validation | `expect_api` | all API tests |
| JSON Schema validation | `framework/api/schemas`, `matches_schema` | contract tests |
| Response time | `ApiResponse.elapsed_ms`, `responds_within` | `test_core_endpoints_respond_within_threshold` |
| Negative & boundary | parametrized suites | price/stock/length/paging boundaries |
| Chaining | token → call, create → read → update → delete | `test_product_crud_lifecycle`, auth flows |
| Reusable clients & assertions | `api/clients`, `assertions/api_assertions.py` | no duplicated validation code |
| Request/response logging | redacted log + per-test exchange log + Allure attachment | failure probes |
| Correlation IDs | `X-Correlation-ID` per request, echoed by app | `test_correlation_id_is_echoed_on_success_and_error` |
| API test data management | factories + backdoor + cleanup | all data-creating tests |

## 8. UI + API integration
All five suggested scenarios implemented (`tests/integration`), plus registration, CSV export,
identical validation and reverse session sharing; cleanup via factories / registry. ✅

## 9. AI integration

| Requirement | Status |
|---|---|
| Separate AI module, swappable provider | ✅ `framework/ai`, `LLMProvider` protocol |
| Test case generator (scenarios, pos/neg/boundary, manual → pytest, coverage suggestions) | ✅ ⚠️ live |
| Failure analyzer (logs, screenshots/traces where supported, API details, root cause, actions, summary) | ✅ ⚠️ live |
| Locator assistant (alternatives, DOM analysis, stable strategies) | ✅ verified candidates ⚠️ live |
| Test data generator (positive/negative/boundary, realistic) | ✅ ⚠️ live |
| Reporting assistant (summary, grouping, recurring) | ✅ grouping/recurring computed without AI; narrative ⚠️ live |
| Assists, never controls; never auto-modifies tests; human approval | ✅ drafts only in `ai_drafts/`, enforced by `write_draft` |
| No secrets/sensitive data sent | ✅ AIClient gate (redaction incl. emails), screenshots opt-in, traces never; scans 0 findings |
| Optional, works when AI unavailable | ✅ NullProvider; whole suite runs with AI off |
| API key in environment only | ✅ `ANTHROPIC_API_KEY` in `.env` / CI secret |

⚠️ No real Claude call yet: needs an `ANTHROPIC_API_KEY`, then
`FW_AI_LIVE=1 uv run pytest tests/ai_live -m ai_live`.

## 10. Pytest & execution management

| Requirement | Evidence |
|---|---|
| Fixtures, setup/teardown, one-time setup | `framework/fixtures/*`; session-scoped tokens/backdoor, app seeded once per run |
| Markers smoke, regression, sanity, UI, API, integration | registered, strict; layer markers + regression automatic |
| Parallel execution | `-n 4` / `-n auto` |
| Environment-specific execution | `--env local|ci|staging` |
| Browser selection | `--browser` |
| Configurable retries, transient infra failures only | `retry:` config + `fixtures/execution.py`; assertions never rerun (proven) |
| Independent, repeatable tests | unique data, no shared totals, repeated runs green |
| Commands `pytest -m smoke`, `tests/ui`, `tests/api`, `tests/integration`, `-m regression --browser chromium`, `-n 4` | all six run green in Phase 10 |

## 11. Reporting & logging
Allure: totals, passed/failed/skipped, duration, details + steps, failure reasons +
categories, screenshots, request/response, environment + browser info; automatic UI failure
attachments; secrets excluded (layered redaction + sanitize pass, scanned). Logs: per-worker
files, redacted. ✅

## 12. Sample test cases
Required ≥ 20 → **151 functional tests** (UI 38, API 96, integration 17) covering every listed
case (valid/invalid login, empty fields, registration, user management, search, filter,
add/edit/delete product; GET/POST/GET-by-id/update/delete user, invalid auth, missing fields,
invalid payload, invalid id, schema validation; the three integration cases). ✅

## 13. Code quality
Modular packages, PEP 8 via ruff (lint + format, clean), type hints throughout, SOLID where
useful (provider protocol, thin adapters), no duplicated validation, configuration separate
from tests, no hard-coded URLs/credentials/test data, documented. ✅
(Static type checking with mypy/pyright is not part of the pipeline - see DEVELOPMENT_STATUS.)

## 14. Development approach
10 phases, each explained, implemented, tested, documented and confirmed;
`DEVELOPMENT_STATUS.md` and `ARCHITECTURE.md` maintained throughout. ✅

## 15. Final deliverables

| Deliverable | Where |
|---|---|
| Python Playwright automation framework | `framework/`, `tests/` |
| Working sample web application + REST API | `sample_application/` |
| UI / API / integration test cases | `tests/ui`, `tests/api`, `tests/integration` |
| AI-powered test assistance | `framework/ai` (⚠️ live call) |
| Allure reporting | `fixtures/reporting.py`, `scripts/report.*` |
| Parallel execution | pytest-xdist + autostart |
| Environment configuration | `config/` |
| Reusable utilities and components | `framework/` |
| Installation and execution guide | `README.md` |
| Architecture documentation | `ARCHITECTURE.md` |
| Sample execution reports | `docs/sample-report/index.html` |
| CI/CD configuration | `.github/` (⚠️ first GitHub run) |
