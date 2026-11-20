# Development Status

_Last updated: 2026-11-20_

## Current state
**All 10 phases complete.** Two items can only be verified with your input (see
"Needs your action"): the first real Claude API call and the first run on GitHub Actions.

| Area | Result of the final regression (Phase 10) |
|---|---|
| Commands from the brief (`-m smoke`, `tests/ui`, `tests/api`, `tests/integration`, `-m regression --browser chromium`, `-n 4`) | all six green: 25 · 38 · 96 · 17 · 151 · 226 (+1 opt-in skip) |
| Whole suite, `-n 4`, Chromium + Firefox + WebKit | 336 passed, 1 skipped - **twice** |
| Same, CI configuration (`--env ci`, random passwords, reruns active) | 336 passed, 1 skipped, **0 reruns needed** |
| Clean copy of the repository (only versionable files), fresh setup | setup self-tests 75/75; whole suite 226 passed, 1 skipped |
| Lint / format (ruff) | clean |
| Secret scans (results, sample report, AI prompts) | 0 findings |

## Phase summary
| Phase | Delivered | Key verification |
|---|---|---|
| 1 Architecture | ARCHITECTURE.md, approved with defaults | - |
| 2 Environment | uv + project-local Python 3.12, layered config, redacting logging | self-tests |
| 3 Sample app | FastAPI + SQLite + Jinja2 shop admin, REST API | 77-check smoke + browser check |
| 4 UI framework | POM, components, autostart, auth via storage state, failure artifacts | 38 UI tests × 3 browsers |
| 5 API framework | HTTPX client, token management, contracts, fluent assertions | 96 API tests, mutation check |
| 6 Integration | 17 cross-layer tests, session sharing both ways | mutation checks |
| 7 Reporting | Allure: steps, attachments, categories, environment, sanitize pass, sample report | secret scans |
| 8 AI | 5 assistants behind a safety gate, CLI, `--ai-analysis` | 30 AI self-tests, prompt scan |
| 9 Parallel & CI | infra-only reruns, run scripts, GitHub Actions | rerun probes, local CI simulation |
| 10 Final | regression marker fix, Windows path safeguard, docs rewrite, traceability, sample report | final regression (above) |

## Defects found and fixed during the project
| Phase | Where | Defect |
|---|---|---|
| 2 | Framework | `.env` silently ignored (parameter shadowed by a local variable) |
| 3 | Sample app | self-lockout guard blocked normal users' profile edits; un-encoded pagination links |
| 4 | Sample app | validation message "greater than 0.0" |
| 4 | Framework | app "stop" killed only the venv launcher; login API calls put the password into traces; same-URL form submit race |
| 5 | Sample app | **ids of deleted rows reused** (stale ids addressed other records) - root cause of a flaky test; malformed-JSON error message |
| 5 | Framework | anonymous API session silently authenticated by a stored login cookie; unchecked `date-time` schema format |
| 6 | Sample app | **inconsistent paging** under concurrent writes (16 items, `total: 15`) |
| 7 | Framework | test names/parameters/messages unredacted in Allure; redaction over-masking fixture names |
| 9 | Config / CI | rerun patterns could never match; assertions could be rerun via exception chain; workflow summary step and `setup-uv@v10` would have failed |
| 10 | Framework | `-m regression` skipped all smoke/sanity tests; AI import failure in deep Windows paths reported as "not installed"; corrupted script commands in README |

## Phase 10 details
- [x] Baseline: files flagged as changed matched the last state; lint + self-tests clean
- [x] Requirements review against the brief → [docs/requirements_traceability.md](docs/requirements_traceability.md)
- [x] Gap closed: `regression` now auto-applied to every UI/API/integration test (151); smoke/sanity are subsets; rule unit-tested
- [x] Final regression (table above)
- [x] Clean-copy installation check: found the Windows 260-char path limit breaking the `anthropic` SDK import in a deeply nested copy (framework correctly fell back to "AI off"); added a setup-script warning and an accurate error message; re-verified from a normal-length path
- [x] Docs: README rewritten as installation & execution guide (+ troubleshooting; two corrupted commands fixed); ARCHITECTURE.md rewritten as-built (62 decisions kept, sorted); traceability matrix; sample report rebuilt from the final run

## Needs your action
| Item | How |
|---|---|
| First real Claude call | Add `ANTHROPIC_API_KEY` to `.env`, then `FW_AI_LIVE=1 uv run pytest tests/ai_live -m ai_live` (one small, low-effort call). Then optionally `FW_AI__ENABLED=true uv run pytest --ai-analysis`. |
| First GitHub Actions run | Create an empty GitHub repository, make the first commit, add the remote and push (I can do the git steps once you give the URL and approve the push). |

## Known issues / accepted limitations
| ID | Issue | Status |
|---|---|---|
| N1 | `C:\Users\sebastianj\.local\bin\python3.12.exe` exists, not managed by uv; unused | Delete manually if not needed |
| N3 | No GitHub remote and no commits yet | Needs your repository + approval |
| N4 | Swagger UI (`/docs`) needs internet (CDN assets) | Accepted |
| N5 | No CSRF protection on web forms (demo app) | Accepted, documented |
| N6 | Playwright traces contain the session cookie and typed test values | Kept only on failure; test accounts only (random per run in CI); never sent to AI |
| N7 | `.claude/launch.json` preview may leave the server child running after `preview_stop` | Stop via port 8000 owner if it happens |
| N8 | App timestamps have no timezone (not RFC 3339) | Accepted for the demo |
| N9 | Redaction also masks `token_type` | Harmless over-masking |
| N10 | Logout does not revoke tokens (stateless JWT) | Accepted for the demo; characterised by a test |
| N11 | JWTs glued together with `-` may be partly visible after redaction | Edge case |
| N12 | Short AI system prompts are below the prompt-cache minimum | Harmless |
| N13 | CI does not publish to GitHub Pages / keep Allure trends across CI runs | Optional follow-up |
| N14 | Windows: project paths longer than ~90 chars break some imports unless long paths are enabled | Setup warns; documented in README troubleshooting |
| N15 | No static type checker (mypy/pyright) in the pipeline - type hints are not machine-verified | Optional follow-up |

## Possible next steps (optional)
1. Connect GitHub and run CI; then optionally publish the Allure report to GitHub Pages with trend history.
2. Run the live AI checks with an API key.
3. Add a static type checker (pyright or mypy) to the `quality` CI job.
4. Point the framework at a real application: add `config/environments/<env>.yaml`, page objects and clients for it.
