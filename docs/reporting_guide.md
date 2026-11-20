# Reporting Guide (Allure)

Every test run writes Allure results automatically - no extra flag needed.

```bash
uv run pytest -n 4                                   # results -> reports/allure-results
powershell -File scripts\report.ps1 -Open            # Windows: build + open the HTML report
bash scripts/report.sh --open                        # Linux/macOS/Git Bash
powershell -File scripts\report.ps1 -SingleFile      # one self-contained index.html to share
```
The report scripts need the Allure CLI (Java 8+). They copy the previous report's
`history/` into the new results, so the **Trend** chart grows run by run.

**Sample:** [docs/sample-report/index.html](sample-report/index.html) - single-file report of
the final Phase 10 run: all suites on Chromium, Firefox and WebKit in parallel (341 tests,
336 passed, 1 opt-in skip) plus **two deliberately failing demo tests** - a UI price mismatch
(run on 3 browsers, with screenshot + DOM snapshot + API exchanges) and an API status mismatch
(redacted request/response) - so you can see what failures look like. Built with
`--tracing off` (no browser traces) and scanned: no passwords or tokens inside. Open it in
a browser (or serve the folder: `python -m http.server -d docs/sample-report`).

## What is in the report

| Requirement | Where |
|---|---|
| Total / passed / failed / skipped / duration | Overview, Graphs, Timeline |
| Test details, steps | Every API call (`GET /api/v1/users`) and page action (`Search products for 'X'`) is a step; setup calls appear too |
| Failure reasons | Error message + stack, grouped on the **Categories** tab |
| Screenshots / traces / video | Attached to failed UI tests (as kept by pytest-playwright) |
| Request & response details | `API exchanges (redacted)` attached to failed tests (or to every API step - see config) |
| Logs | `log` attachment = the test's captured log lines (redacted at source) |
| Environment & browser info | Environment widget: env, base URL, browsers, headless, workers, Python/Pytest/Playwright, OS, run id, command |
| Grouping | Behaviors: **epic** = layer (UI / API / UI + API integration / Framework), **feature** = test module; **severity**: smoke = critical, others normal; markers become **tags** |

### Failure categories (first match wins)
| Category | Meaning |
|---|---|
| Environment / infrastructure problems | App unreachable, setup API failed, browser crashed - rerun/fix the environment |
| UI element not found / timeout | A Playwright action timed out - locator changed, element missing or page slow |
| Product defects (assertion failed) | The application did not do what the test expected |
| Test defects (broken test code) | Any other exception in test/framework code |

## Configuration (`config/config.yaml` → `reporting:`)

| Key | Default | Effect |
|---|---|---|
| `allure_enabled` | `true` | write results on every run (`--alluredir` overrides the folder) |
| `clean_results` | `true` | wipe old results once per run (main process only - safe with `-n`) |
| `attach_api_exchanges` | `on-failure` | `always` = every API step gets its request/response; `off` = never |
| `attach_browser_artifacts` | `true` | attach screenshot/trace/video of failed UI tests |

Tracing/video/screenshot capture itself is configured under `browser:` (or `--tracing`, `--video`, `--screenshot`).

## Secrets - three layers of protection

1. **At the source:** log records, API exchange renders and every attachment/step title go
   through the redactor (passwords, tokens, cookies, Authorization headers, API keys, known secret values).
2. **Steps record no arguments:** `framework.reporting.step_method` titles show only what the
   template names (e.g. the email), never the password argument.
3. **Final pass:** after all workers finish, every result/container file is re-redacted
   (test names, parameters - masked by parameter name - and failure messages).

**Exception - Playwright traces** (`trace.zip`) contain the session cookie and anything typed
into fields. They are only kept for failed tests, contain test accounts only, and should be
treated as sensitive (see DEVELOPMENT_STATUS N6). Use `--tracing off` for reports you share.

## Adding steps to your own page objects / helpers

```python
from framework.reporting import step, step_method, attach_text

class CheckoutPage(BasePage):
    @step_method("Pay order {order_id}")          # title from arguments you choose
    def pay(self, order_id: str, card_cvc: str) -> None: ...   # card_cvc never appears

with step("Prepare 3 discounted products"):       # ad-hoc step inside a test
    ...
attach_text("Pricing rule", rule_text)            # redacted text attachment
```
