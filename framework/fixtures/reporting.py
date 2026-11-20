"""Allure integration plugin.

* Results are written on every run to ``reporting.allure_results_dir`` (no flag needed);
  ``--alluredir`` still overrides. Old results are removed ONCE per run by the main
  process before xdist workers start (allure's own --clean-alluredir would let a late
  worker delete results an early worker already wrote).
* Labels: epic = test layer, feature = test module, severity from markers.
* Failed UI tests get the screenshot / trace / video kept by pytest-playwright.
* Failed tests get their (redacted) API exchanges.
* environment.properties + categories.json describe the run.
"""

from __future__ import annotations

import os
import platform
import shutil
import sys
from datetime import UTC, datetime
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

import pytest
from playwright.sync_api import BrowserContext, Page

from framework.api.http_client import ApiExchangeLog
from framework.core.app_server import RUN_ID_ENV
from framework.core.logging_config import get_logger
from framework.core.paths import PROJECT_ROOT, resolve_project_path
from framework.core.redaction import get_redactor
from framework.fixtures.core import SETTINGS_KEY, bootstrap
from framework.reporting.allure_helpers import attach_file, attach_text
from framework.reporting.run_metadata import write_categories, write_environment
from framework.reporting.sanitize import sanitize_results

log = get_logger(__name__)

_REPORTS = pytest.StashKey[dict[str, pytest.TestReport]]()
_OUTPUT_PATH = pytest.StashKey[str]()
_STARTED = pytest.StashKey[str]()

_EPICS = {
    "ui": "UI",
    "api": "API",
    "integration": "UI + API integration",
    "unit": "Framework",
    "ai_live": "AI (live)",
}
_SEVERITY = {"smoke": "critical", "sanity": "normal", "regression": "normal"}
_ACRONYMS = {"Ui": "UI", "Api": "API", "Csv": "CSV"}


def _is_worker() -> bool:
    return "PYTEST_XDIST_WORKER" in os.environ


def _allure_dir(config: pytest.Config) -> Path | None:
    value = getattr(config.option, "allure_report_dir", None)
    return Path(value).absolute() if value else None


# ----------------------------------------------------------------- configure
@pytest.hookimpl(tryfirst=True)  # must run before allure-pytest reads --alluredir
def pytest_configure(config: pytest.Config) -> None:
    settings = bootstrap(config)
    reporting = settings.reporting
    if not hasattr(config.option, "allure_report_dir"):
        return  # allure-pytest not installed / disabled with -p no:allure_pytest
    we_chose_dir = False
    if reporting.allure_enabled and not config.option.allure_report_dir:
        config.option.allure_report_dir = str(resolve_project_path(reporting.allure_results_dir))
        we_chose_dir = True
    results = _allure_dir(config)
    if results is None or _is_worker() or config.option.collectonly:
        return
    if we_chose_dir and reporting.clean_results and results.is_dir():
        shutil.rmtree(results, ignore_errors=True)
    write_categories(results)
    config.stash[_STARTED] = datetime.now(UTC).isoformat(timespec="seconds")


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Group tests in Allure's Behaviors view: epic = layer, feature = module."""
    tests_root = PROJECT_ROOT / "tests"
    for item in items:
        try:
            parts = Path(item.path).resolve().relative_to(tests_root).parts
        except ValueError:
            continue
        if not parts:
            continue
        epic = _EPICS.get(parts[0])
        if epic:
            item.add_marker(pytest.mark.allure_label(epic, label_type="epic"))
        feature = " ".join(
            w.capitalize() for w in Path(parts[-1]).stem.removeprefix("test_").split("_")
        )
        for word, acronym in _ACRONYMS.items():
            feature = feature.replace(word, acronym)
        item.add_marker(pytest.mark.allure_label(feature, label_type="feature"))
        severity = next((s for m, s in _SEVERITY.items() if item.get_closest_marker(m)), "normal")
        item.add_marker(pytest.mark.allure_label(severity, label_type="severity"))


# ------------------------------------------------------------------ per test
@pytest.hookimpl(wrapper=True)
def pytest_runtest_makereport(item: pytest.Item, call: pytest.CallInfo[Any]) -> Any:
    report = yield
    item.stash.setdefault(_REPORTS, {})[report.when] = report
    output_path = getattr(item, "funcargs", {}).get("output_path")
    if output_path:
        item.stash[_OUTPUT_PATH] = output_path
    if report.failed and report.when in ("setup", "call"):
        _attach_api_exchanges(item)
    if report.failed and report.when == "call":
        _attach_dom_snapshots(item)  # pages are still open during the call report
    return report


@pytest.hookimpl(wrapper=True)
def pytest_runtest_teardown(item: pytest.Item, nextitem: pytest.Item | None) -> Any:
    result = yield  # fixtures are torn down: pytest-playwright has saved its artifacts
    reports = item.stash.get(_REPORTS, {})
    if any(r.failed for r in reports.values()):
        _attach_browser_artifacts(item)
    return result


def _attach_api_exchanges(item: pytest.Item) -> None:
    settings = item.config.stash.get(SETTINGS_KEY, None)
    if settings is None or settings.reporting.attach_api_exchanges != "on-failure":
        return  # "always": already attached per API step; "off": never
    exchange_log = getattr(item, "funcargs", {}).get("api_log")
    if isinstance(exchange_log, ApiExchangeLog) and exchange_log.entries:
        attach_text("API exchanges (redacted)", exchange_log.render())


_DOM_LIMIT = 300_000


def _open_pages(item: pytest.Item) -> list[Page]:
    pages: list[Page] = []
    for value in getattr(item, "funcargs", {}).values():
        candidates = value.pages if isinstance(value, BrowserContext) else [value]
        for candidate in candidates:
            if isinstance(candidate, Page) and not candidate.is_closed() and candidate not in pages:
                pages.append(candidate)
    return pages[:3]


def _attach_dom_snapshots(item: pytest.Item) -> None:
    settings = item.config.stash.get(SETTINGS_KEY, None)
    if settings is None or not settings.reporting.attach_dom_snapshot:
        return
    for page in _open_pages(item):
        try:
            html = page.content()
            url = page.url
        except Exception as exc:  # page crashed / navigating - evidence is best effort
            log.debug("DOM snapshot skipped: %r", exc)
            continue
        if len(html) > _DOM_LIMIT:
            html = html[:_DOM_LIMIT] + f"\n<!-- truncated, {len(html)} chars -->"
        # Plain text on purpose: an HTML attachment would execute inside the report.
        attach_text(f"DOM snapshot (redacted) - {url}", html)


def _attach_browser_artifacts(item: pytest.Item) -> None:
    settings = item.config.stash.get(SETTINGS_KEY, None)
    if settings is None or not settings.reporting.attach_browser_artifacts:
        return
    folder = item.stash.get(_OUTPUT_PATH, None)
    if not folder or not Path(folder).is_dir():
        return
    for file in sorted(Path(folder).iterdir()):
        if file.is_file():
            label = {".png": "Screenshot", ".zip": "Playwright trace", ".webm": "Video"}.get(
                file.suffix.lower(), "Artifact"
            )
            attach_file(file, name=f"{label} - {file.name}")
    if any(f.suffix == ".zip" for f in Path(folder).iterdir()):
        attach_text(
            "How to open the trace",
            "Download the trace .zip and run:\n  uv run playwright show-trace <file>.zip\n"
            "or drop it on https://trace.playwright.dev (opens locally in your browser).",
        )


# ------------------------------------------------------------------ finish
def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    config = session.config
    results = _allure_dir(config)
    if results is None or _is_worker() or config.option.collectonly:
        return
    settings = config.stash[SETTINGS_KEY]
    workers = getattr(config.option, "numprocesses", None)
    write_environment(
        results,
        {
            "Environment": settings.env,
            "Base.URL": settings.app.base_url,
            "Browsers": ", ".join(config.option.browser or [settings.browser.name]),
            "Headless": not config.option.headed,
            "Parallel.workers": workers or 1,
            "Python": platform.python_version(),
            "Pytest": _version("pytest"),
            "Playwright": _version("playwright"),
            "OS": f"{platform.system()} {platform.release()}",
            "Run.ID": os.environ.get(RUN_ID_ENV, "-"),
            "Started.UTC": config.stash.get(_STARTED, "-"),
            "Command": get_redactor().redact_text(" ".join(["pytest", *sys.argv[1:]]))[:300],
        },
    )
    changed = sanitize_results(results)  # safety net: names/params/messages too
    log.info("Allure results written to %s (%d file(s) redacted)", results, changed)


def _version(package: str) -> str:
    try:
        return version(package)
    except PackageNotFoundError:
        return "-"
