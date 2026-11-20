# AI Assistance Guide (Claude)

AI in this framework is **optional and advisory**. It never decides pass/fail, never
changes code on its own, and the framework behaves identically when it is off.

## Turn it on

```bash
# .env
ANTHROPIC_API_KEY=sk-ant-...        # from https://console.anthropic.com
FW_AI__ENABLED=true
```
```bash
uv run python -m framework.ai status      # shows config; never prints the key
```
Defaults (`config/config.yaml` → `ai:`): model **`claude-opus-5-5`** (most capable Opus,
$4 / $20 per million input/output tokens), `effort: high`, at most **20 calls per run**,
screenshots **not** sent. To reduce cost set `model: claude-sonnet-5-5` ($2 / $10) or
`claude-haiku-5-5`, and/or `effort: medium`/`low`. Any problem (no key, network, rate limit,
refusal, budget) turns AI off for that call and is reported - nothing crashes.

## The five assistants

| Assistant | Command | Output |
|---|---|---|
| **Test case generator** | `python -m framework.ai generate-tests --requirements docs/req.md [--compare-existing]` | Scenarios (positive / negative / boundary / edge, level, priority, steps, data), assumptions, coverage gaps, automation suggestions → `reports/ai/test_scenarios_*.md/.json` |
| Manual → pytest | `python -m framework.ai convert-manual --input manual_cases.txt` | **Draft** module in `ai_drafts/` using our fixtures/pages/assertions, with `REVIEW` notes and `TODO(human)` markers |
| **Failure analyzer** | `pytest --ai-analysis` or `python -m framework.ai analyze-failures [--max 5]` | Per failure: category (product / test / environment / flaky / unknown), root cause, quoted evidence, actions, locator suggestions, missing evidence, confidence → `reports/ai/failure_analysis_*.md` |
| **Locator assistant** | `python -m framework.ai suggest-locators --html dom.txt --locator "..." --intent "..."` or in code `LocatorAssistant(ai, out).suggest_for_page(page, failed, intent)` | Ranked role/label/test-id candidates; on a live page each is **verified** (match count) |
| **Test data generator** | `python -m framework.ai generate-data --entity product --count 5` | Valid / invalid (one rule broken each) / boundary records → `ai_drafts/data/*.json`; `materialize()` fills `{unique}` placeholders |
| **Reporting assistant** | `pytest --ai-analysis` or `python -m framework.ai summarize` | **Always** (no AI needed): stats, failures grouped by normalised error signature, new / recurring / flaky from Allure history. **With AI**: headline, health, findings, likely cause + owner per group, next steps → `reports/ai/run_summary_*.md` |

All commands use the last Allure results (`reports/allure-results`) by default.

## What the AI sees - and what it never sees

Evidence is extracted **locally** (`framework/ai/evidence.py`) from the Allure results:
failure message, trimmed stack trace, steps, redacted API exchanges, captured log, the
redacted **DOM snapshot** taken at the moment of a UI failure, and from Playwright traces
only console errors and failed (4xx/5xx) requests.

Every request then passes the **AIClient gate** (`framework/ai/client.py`):

1. **Redaction** of system prompt + prompt: configured passwords, tokens/JWTs, Authorization
   headers, cookies, API keys, `password=...`-style values **and emails** (`<email>`).
2. **Screenshots dropped** unless `ai.send_screenshots: true` (they may show data).
3. **Raw traces never sent** (they contain cookies and typed values).
4. **Budget**: `ai.max_calls_per_run`; the failure analyzer also caps analyses (`--max`).
5. **Audit**: the exact text sent is written to `reports/ai/requests/*.md` - check it any time.
6. `.env`, source code and test data files are never sent unless you pass a file to a command
   yourself (e.g. requirements).

## Human approval - enforced, not just promised

* Generated code and data go **only** to `ai_drafts/` - `write_draft()` refuses `tests/`,
  `framework/` and `config/`, and pytest never collects `ai_drafts/`.
* Drafts carry a `DRAFT ... NOT REVIEWED` header; code that does not parse is saved as
  `.py.txt` so it cannot be imported.
* Analyses are markdown reports marked *Advisory only*.
* To adopt a draft: review it, complete `TODO(human)`, run it, move it into `tests/` yourself.

## Architecture

```
framework/ai/
├── providers/base.py     LLMProvider protocol (provider-neutral request/usage types)
├── providers/claude.py   Anthropic SDK - the only file importing `anthropic`
├── providers/null.py     AI off
├── client.py             AIClient gate (redact, image policy, budget, audit, never raises)
├── factory.py            settings -> provider (any misconfiguration -> NullProvider)
├── evidence.py           Allure results -> compact, local evidence
├── prompts/*.md          versioned prompts (review prompt changes like code)
├── services/             test_cases, failures, locators, data, run_summary
└── cli.py                python -m framework.ai ...
```
**Another LLM provider** = one new module implementing `generate(request, schema)` + one
branch in `factory.build_provider`. Services, gate, CLI and pytest plugin stay unchanged.

Claude specifics (`providers/claude.py`): structured output via `beta.messages.parse(
output_format=<pydantic model>)` (validated, typed answers), `output_config.effort`,
`cache_control` on the stable system prompt, server-side refusal **fallback** (on models
that support it), SDK retries for 429/5xx/connection errors, typed error mapping.

## Testing the AI layer

* `pytest -m unit` - 30+ self-tests with fake providers: redaction before sending, screenshot
  policy, budget, error handling, request shape (model, schema, effort, caching, fallback,
  images), evidence extraction, draft safety, locator verification, grouping, CLI with AI off.
* Live check (real, billed calls; tiny and low-effort):
  ```bash
  FW_AI_LIVE=1 uv run pytest tests/ai_live -m ai_live
  ```
