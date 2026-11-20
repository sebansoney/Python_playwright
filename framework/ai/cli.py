"""Command line for the AI assistants:  uv run python -m framework.ai <command> ...

Every command works without AI: it then explains why AI is off and, where possible,
still produces the non-AI part (e.g. the computed run summary). AI output goes to
reports/ai/ (analyses) or ai_drafts/ (code/data drafts) - never into tests/.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from config.settings import Settings, load_settings
from framework.ai.client import AIClient
from framework.ai.factory import build_ai_client
from framework.core.logging_config import configure_logging
from framework.core.paths import PROJECT_ROOT, resolve_project_path
from framework.core.redaction import configure_redactor


def _bootstrap(env: str | None) -> tuple[Settings, AIClient]:
    settings = load_settings(env)
    configure_redactor(
        sensitive_keys=settings.redaction.sensitive_keys,
        mask=settings.redaction.mask,
        secrets=settings.secret_values(),
    )
    configure_logging(
        resolve_project_path(settings.reporting.logs_dir), settings.reporting.log_level
    )
    return settings, build_ai_client(settings)


def _dirs(settings: Settings) -> tuple[Path, Path]:
    return resolve_project_path(settings.ai.output_dir), resolve_project_path(
        settings.ai.drafts_dir
    )


def _off(ai: AIClient) -> None:
    print(f"AI is off: {ai.disabled_reason}")


def _usage(ai: AIClient) -> None:
    u = ai.total_usage
    if ai.calls_made:
        print(
            f"AI calls: {ai.calls_made} | tokens in {u.input_tokens} "
            f"(cache read {u.cache_read_tokens}) / out {u.output_tokens} | "
            f"model {u.model or '-'} | requests logged in reports/ai/requests/"
        )


def cmd_status(settings: Settings, ai: AIClient, _: argparse.Namespace) -> int:
    key = bool(settings.anthropic_api_key and settings.anthropic_api_key.get_secret_value())
    print(
        f"enabled={settings.ai.enabled} provider={settings.ai.provider} model={settings.ai.model} "
        f"effort={settings.ai.effort} api_key_set={key} "
        f"send_screenshots={settings.ai.send_screenshots} "
        f"budget={settings.ai.max_calls_per_run} calls/run"
    )
    print("AI is ready." if ai.enabled else f"AI is off: {ai.disabled_reason}")
    return 0


def cmd_generate_tests(settings: Settings, ai: AIClient, args: argparse.Namespace) -> int:
    from framework.ai.services.test_cases import TestCaseGenerator, existing_test_names

    out, drafts = _dirs(settings)
    if not ai.enabled:
        _off(ai)
        return 0
    text = Path(args.requirements).read_text(encoding="utf-8")
    existing = existing_test_names() if args.compare_existing else None
    outcome = TestCaseGenerator(ai, out, drafts).generate_scenarios(text, existing)
    print(
        f"{len(outcome.value.scenarios)} scenarios written to {out}"
        if outcome.ok and outcome.value
        else f"No scenarios: {outcome.message}"
    )
    return 0 if outcome.ok else 1


def cmd_convert_manual(settings: Settings, ai: AIClient, args: argparse.Namespace) -> int:
    from framework.ai.services.test_cases import TestCaseGenerator

    out, drafts = _dirs(settings)
    if not ai.enabled:
        _off(ai)
        return 0
    outcome, path = TestCaseGenerator(ai, out, drafts).manual_to_pytest(
        Path(args.input).read_text(encoding="utf-8")
    )
    if path:
        print(
            f"DRAFT written to {path.relative_to(PROJECT_ROOT)}\n"
            "Review it, complete the TODO(human) items, run it, then move it into tests/ yourself."
        )
        return 0
    print(f"No draft: {outcome.message}")
    return 1


def cmd_analyze(settings: Settings, ai: AIClient, args: argparse.Namespace) -> int:
    from framework.ai.services.failures import FailureAnalyzer

    out, _ = _dirs(settings)
    if not ai.enabled:
        _off(ai)
        return 0
    results = (
        Path(args.results)
        if args.results
        else resolve_project_path(settings.reporting.allure_results_dir)
    )
    report, path = FailureAnalyzer(ai, out).analyze_run(results, max_failures=args.max)
    done = sum(1 for f in report.analyzed if f.analysis)
    print(f"{report.failures} failure(s), {done} analyzed -> {path.relative_to(PROJECT_ROOT)}")
    return 0


def cmd_locators(settings: Settings, ai: AIClient, args: argparse.Namespace) -> int:
    from framework.ai.services.locators import LocatorAssistant

    out, _ = _dirs(settings)
    if not ai.enabled:
        _off(ai)
        return 0
    html = Path(args.html).read_text(encoding="utf-8", errors="replace")
    outcome = LocatorAssistant(ai, out).suggest(args.locator, args.intent, html)
    if not (outcome.ok and outcome.value):
        print(f"No suggestions: {outcome.message}")
        return 1
    print(f"Diagnosis: {outcome.value.diagnosis}")
    for c in outcome.value.candidates:
        print(f"  [{c.stability}] {c.as_code()}  - {c.rationale}")
    print("(Unverified: LocatorAssistant.suggest_for_page() counts matches on a live page.)")
    return 0


def cmd_data(settings: Settings, ai: AIClient, args: argparse.Namespace) -> int:
    from framework.ai.services.data import TestDataGenerator

    _, drafts = _dirs(settings)
    if not ai.enabled:
        _off(ai)
        return 0
    outcome, path = TestDataGenerator(ai, drafts).generate(args.entity, args.count)
    if path and outcome.value:
        v = outcome.value
        print(
            f"{len(v.valid)} valid, {len(v.invalid)} invalid, "
            f"{len(v.boundary)} boundary records -> "
            f"{path.relative_to(PROJECT_ROOT)}"
        )
        return 0
    print(f"No data: {outcome.message}")
    return 1


def cmd_summarize(settings: Settings, ai: AIClient, args: argparse.Namespace) -> int:
    from framework.ai.services.run_summary import ReportAssistant

    out, _ = _dirs(settings)
    results = (
        Path(args.results)
        if args.results
        else resolve_project_path(settings.reporting.allure_results_dir)
    )
    local, outcome, path = ReportAssistant(ai, out).summarize(
        results, resolve_project_path(settings.reporting.allure_report_dir)
    )
    print(
        f"{local.run.total} tests, {len(local.groups)} failure group(s) -> "
        f"{path.relative_to(PROJECT_ROOT)}"
        + ("" if outcome.ok else f"  (AI narrative: {outcome.message})")
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m framework.ai", description="AI assistants (optional, advisory)"
    )
    p.add_argument("--env", help="config environment (default: TEST_ENV or local)")
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("status", help="show AI configuration")
    g = sub.add_parser(
        "generate-tests", help="requirements file -> test scenarios (markdown + json)"
    )
    g.add_argument("--requirements", required=True)
    g.add_argument(
        "--compare-existing",
        action="store_true",
        help="send existing test names to avoid duplicates",
    )
    c = sub.add_parser("convert-manual", help="manual test cases -> pytest DRAFT in ai_drafts/")
    c.add_argument("--input", required=True)
    a = sub.add_parser("analyze-failures", help="analyze failed tests from Allure results")
    a.add_argument("--results")
    a.add_argument("--max", type=int, default=5, help="max failures to analyze (cost control)")
    loc = sub.add_parser("suggest-locators", help="broken locator + saved DOM -> alternatives")
    loc.add_argument(
        "--html", required=True, help="DOM snapshot file (e.g. from an Allure attachment)"
    )
    loc.add_argument("--locator", required=True)
    loc.add_argument("--intent", required=True, help="what the step is trying to do")
    d = sub.add_parser("generate-data", help="valid/invalid/boundary data DRAFT for an entity")
    d.add_argument("--entity", choices=["product", "user"], required=True)
    d.add_argument("--count", type=int, default=5)
    s = sub.add_parser("summarize", help="run summary: computed groups (+ AI narrative if enabled)")
    s.add_argument("--results")
    return p


COMMANDS = {
    "status": cmd_status,
    "generate-tests": cmd_generate_tests,
    "convert-manual": cmd_convert_manual,
    "analyze-failures": cmd_analyze,
    "suggest-locators": cmd_locators,
    "generate-data": cmd_data,
    "summarize": cmd_summarize,
}


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    settings, ai = _bootstrap(args.env)
    code = COMMANDS[args.command](settings, ai, args)
    _usage(ai)
    return code


if __name__ == "__main__":
    sys.exit(main())
