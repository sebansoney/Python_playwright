"""Opt-in pytest integration of the AI assistants.

``pytest --ai-analysis``: after the run (main process, after Allure results are written and
sanitized) the failure analyzer and the run summary are produced in reports/ai/. The run's
exit status never depends on AI. Without the flag nothing AI-related happens.

``ai`` fixture: an AIClient for interactive debugging, e.g. the locator assistant.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from config.settings import Settings
from framework.ai.client import AIClient
from framework.ai.factory import build_ai_client
from framework.core.logging_config import get_logger
from framework.core.paths import PROJECT_ROOT, resolve_project_path
from framework.fixtures.core import SETTINGS_KEY

log = get_logger(__name__)
_OUTPUTS = pytest.StashKey[list[str]]()


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.getgroup("framework").addoption(
        "--ai-analysis",
        action="store_true",
        default=False,
        help="After the run: AI failure analysis + run summary (needs ai.enabled + API key).",
    )


@pytest.fixture(scope="session")
def ai(settings: Settings) -> AIClient:
    """AI client for debugging helpers inside tests (disabled -> harmless no-op answers)."""
    return build_ai_client(settings)


@pytest.hookimpl(trylast=True)  # after the reporting plugin wrote + sanitized the results
def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    config = session.config
    if not config.getoption("--ai-analysis") or "PYTEST_XDIST_WORKER" in os.environ:
        return
    results_dir = getattr(config.option, "allure_report_dir", None)
    if not results_dir:
        return
    settings: Settings = config.stash[SETTINGS_KEY]
    outputs: list[str] = []
    try:
        from framework.ai.services.failures import FailureAnalyzer
        from framework.ai.services.run_summary import ReportAssistant

        client = build_ai_client(settings)
        out_dir = resolve_project_path(settings.ai.output_dir)
        _, _summary, summary_path = ReportAssistant(client, out_dir).summarize(
            Path(results_dir), resolve_project_path(settings.reporting.allure_report_dir)
        )
        outputs.append(f"run summary: {summary_path.relative_to(PROJECT_ROOT)}")
        if not client.enabled:
            outputs.append(f"AI is off ({client.disabled_reason}) - computed summary only")
        elif exitstatus != 0:
            report, path = FailureAnalyzer(client, out_dir).analyze_run(Path(results_dir))
            outputs.append(
                f"failure analysis ({report.failures} failure(s)): {path.relative_to(PROJECT_ROOT)}"
            )
    except Exception as exc:  # AI must never break a run
        log.exception("AI analysis failed")
        outputs.append(f"AI analysis failed: {exc!r}")
    config.stash[_OUTPUTS] = outputs


def pytest_terminal_summary(
    terminalreporter: pytest.TerminalReporter, config: pytest.Config
) -> None:
    outputs = config.stash.get(_OUTPUTS, None)
    if outputs:
        terminalreporter.section("AI assistance (advisory)")
        for line in outputs:
            terminalreporter.write_line(line)
