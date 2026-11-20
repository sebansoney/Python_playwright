"""Self-tests for the AI services with a scripted provider (no network, no app)."""

from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel

from framework.ai.client import AIClient
from framework.ai.evidence import AllureResults
from framework.ai.providers.base import LLMRequest, LLMUsage
from framework.ai.providers.null import NullProvider
from framework.ai.services.common import UnsafeDraftLocationError, write_draft
from framework.ai.services.data import FieldValue, materialize
from framework.ai.services.failures import FailureAnalysis, FailureAnalyzer
from framework.ai.services.locators import LocatorAssistant, LocatorCandidate, LocatorSuggestions
from framework.ai.services.run_summary import ExecutionSummary, ReportAssistant, signature
from framework.ai.services.test_cases import PytestDraft, TestCaseGenerator
from framework.core.paths import PROJECT_ROOT


class ScriptedProvider:
    """Returns a prepared answer per schema and records the requests."""

    name = "scripted"
    model = "scripted"

    def __init__(self, answers: dict[type, BaseModel]) -> None:
        self.answers = answers
        self.requests: list[LLMRequest] = []

    def generate(self, request: LLMRequest, schema: type[Any]) -> tuple[Any, LLMUsage]:
        self.requests.append(request)
        return self.answers[schema], LLMUsage(model="scripted")


def _ai(
    answers: dict[type, BaseModel], tmp_path: Path, **kw: Any
) -> tuple[AIClient, ScriptedProvider]:
    provider = ScriptedProvider(answers)
    return AIClient(provider=provider, audit_dir=tmp_path / "req", **kw), provider


# ------------------------------------------------------------ evidence
def _allure_results(folder: Path, messages: list[str]) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "api.txt").write_text("GET /api/v1/users/9 -> HTTP 404", encoding="utf-8")
    (folder / "log.txt").write_text("12:00 INFO something", encoding="utf-8")
    (folder / "dom.txt").write_text("<button>Save changes</button>", encoding="utf-8")
    (folder / "shot.png").write_bytes(b"\x89PNG-fake")
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as z:
        z.writestr(
            "trace.trace",
            json.dumps(
                {"type": "console", "messageType": "error", "text": "TypeError: x is undefined"}
            )
            + "\n",
        )
        z.writestr(
            "trace.network",
            json.dumps(
                {
                    "type": "resource-snapshot",
                    "snapshot": {
                        "request": {"method": "POST", "url": "http://x/api"},
                        "response": {"status": 500},
                    },
                }
            )
            + "\n",
        )
    (folder / "trace.zip").write_bytes(buffer.getvalue())
    for i, message in enumerate(messages):
        result = {
            "name": f"test_{i}",
            "fullName": f"tests.ui.test_x#test_{i}",
            "status": "failed",
            "historyId": f"h{i}",
            "start": 1000,
            "stop": 3000,
            "statusDetails": {"message": message, "trace": "Traceback ..."},
            "labels": [{"name": "epic", "value": "UI"}, {"name": "feature", "value": "Products"}],
            "steps": [{"name": "Open page /products", "status": "passed", "steps": []}],
            "attachments": [
                {"name": "API exchanges (redacted)", "source": "api.txt"},
                {"name": "log", "source": "log.txt"},
                {
                    "name": "DOM snapshot (redacted) - http://127.0.0.1:8000/products",
                    "source": "dom.txt",
                },
                {"name": "Screenshot - test-failed-1.png", "source": "shot.png"},
                {"name": "Playwright trace - trace.zip", "source": "trace.zip"},
            ],
        }
        (folder / f"r{i}-result.json").write_text(json.dumps(result), encoding="utf-8")
    passed = {"name": "ok", "fullName": "t#ok", "status": "passed", "start": 1000, "stop": 2000}
    (folder / "p-result.json").write_text(json.dumps(passed), encoding="utf-8")
    (folder / "environment.properties").write_text(
        "Environment=local\nBrowsers=chromium\n", encoding="utf-8"
    )
    return folder


def test_evidence_reader_extracts_everything_useful(tmp_path: Path) -> None:
    run = AllureResults(
        _allure_results(tmp_path / "res", ["AssertionError: expected 11.00"])
    ).load()

    assert (run.total, run.by_status) == (2, {"failed": 1, "passed": 1})
    ev = run.failures[0]
    assert ev.api_exchanges.startswith("GET /api/v1/users/9")
    assert ev.dom_url == "http://127.0.0.1:8000/products"
    assert ev.screenshot == b"\x89PNG-fake"
    assert ev.trace_findings == [
        "console.error: TypeError: x is undefined",
        "HTTP 500 POST http://x/api",
    ]
    assert "Open page /products [passed]" in ev.to_prompt()


# ------------------------------------------------------------ failures
ANALYSIS = FailureAnalysis(
    category="product_defect",
    probable_root_cause="Price not updated",
    evidence=["actual 10.00"],
    suggested_actions=["Check PATCH handler"],
    locator_suggestions=[],
    missing_evidence=[],
    confidence="high",
)


def test_failure_analyzer_writes_report_and_respects_limits(tmp_path: Path) -> None:
    results = _allure_results(
        tmp_path / "res", ["AssertionError: a", "AssertionError: b", "AssertionError: c"]
    )
    ai, provider = _ai({FailureAnalysis: ANALYSIS}, tmp_path, send_images=False)

    report, path = FailureAnalyzer(ai, tmp_path / "out").analyze_run(results, max_failures=2)

    assert len(provider.requests) == 2  # cost control
    assert [f.analysis is not None for f in report.analyzed] == [True, True, False]
    assert "over the per-run limit" in report.analyzed[2].skipped_reason
    text = path.read_text(encoding="utf-8")
    assert "Price not updated" in text
    assert "Advisory only" in text
    assert provider.requests[0].images == ()  # screenshots not allowed by default
    assert "TypeError: x is undefined" in provider.requests[0].prompt


# ------------------------------------------------------------ test cases
def test_manual_to_pytest_writes_only_reviewable_drafts(tmp_path: Path) -> None:
    good = PytestDraft(
        module_name="Login Tests", code="def test_x():\n    assert True\n", notes=["check data"]
    )
    ai, _ = _ai({PytestDraft: good}, tmp_path)
    gen = TestCaseGenerator(ai, tmp_path / "out", tmp_path / "drafts")

    _, path = gen.manual_to_pytest("TC-1 login works")

    assert path is not None
    assert path.name == "test_login_tests.py"
    assert path.parent == tmp_path / "drafts"
    content = path.read_text(encoding="utf-8")
    assert content.startswith('"""DRAFT generated by AI')
    assert "# REVIEW: check data" in content


def test_unparseable_draft_is_kept_but_not_importable(tmp_path: Path) -> None:
    broken = PytestDraft(module_name="test_broken", code="def test_x(:\n", notes=[])
    ai, _ = _ai({PytestDraft: broken}, tmp_path)

    _, path = TestCaseGenerator(ai, tmp_path / "out", tmp_path / "drafts").manual_to_pytest("x")

    assert path is not None
    assert path.name == "test_broken.py.txt"
    assert "does not parse" in path.read_text(encoding="utf-8")


@pytest.mark.parametrize("folder", ["tests", "framework", "config", "tests/ui"])
def test_ai_output_can_never_be_written_into_project_code(folder: str) -> None:
    with pytest.raises(UnsafeDraftLocationError):
        write_draft(PROJECT_ROOT / folder, "test_evil.py", "x = 1")


# ------------------------------------------------------------ locators
class FakeLocator:
    def __init__(self, count: int) -> None:
        self._count = count

    def count(self) -> int:
        if self._count < 0:
            raise ValueError("invalid selector")
        return self._count


class FakePage:
    def get_by_role(self, role: str, **kw: Any) -> FakeLocator:
        return FakeLocator(1 if (role, kw.get("name")) == ("button", "Save changes") else 0)

    def get_by_text(self, text: str, **kw: Any) -> FakeLocator:
        return FakeLocator(3)

    def locator(self, css: str) -> FakeLocator:
        return FakeLocator(-1)


def test_locator_candidates_are_built_safely_and_verified() -> None:
    suggestions = LocatorSuggestions(
        diagnosis="button renamed",
        candidates=[
            LocatorCandidate(
                strategy="text",
                value="Save",
                name="",
                exact=False,
                rationale="t",
                stability="medium",
            ),
            LocatorCandidate(
                strategy="css", value="##bad", name="", exact=False, rationale="c", stability="low"
            ),
            LocatorCandidate(
                strategy="role",
                value="button",
                name="Save changes",
                exact=True,
                rationale="r",
                stability="high",
            ),
        ],
    )

    verified = LocatorAssistant.verify(FakePage(), suggestions)

    assert verified[0].code == 'page.get_by_role("button", name="Save changes", exact=True)'
    assert verified[0].matches == 1  # unique match ranked first
    assert {v.matches for v in verified[1:]} == {3, -1}  # ambiguous / invalid are flagged


# ------------------------------------------------------------ data
def test_generated_data_gets_unique_values_and_real_types() -> None:
    fields = [
        FieldValue(field="sku", value='"AI-{unique}"'),
        FieldValue(field="price", value="12.5"),
        FieldValue(field="description", value="null"),
        FieldValue(field="name", value="plain text"),
    ]

    first, second = materialize(fields), materialize(fields)

    assert first["sku"] != second["sku"]
    assert str(first["sku"]).startswith("AI-")
    assert (first["price"], first["description"], first["name"]) == (12.5, None, "plain text")


# ------------------------------------------------------------ run summary
def test_signature_groups_failures_that_differ_only_in_data() -> None:
    a = signature("AssertionError: Locator expected 'AT-1A2B3C4D' to have text '11.00' (row 3)")
    b = signature("AssertionError: Locator expected 'AT-9F8E7D6C' to have text '12.50' (row 7)")
    assert a == b


def test_run_summary_detects_recurring_and_works_without_ai(tmp_path: Path) -> None:
    results = _allure_results(
        tmp_path / "res", ["AssertionError: price 1", "AssertionError: price 2"]
    )
    report_dir = tmp_path / "report"
    (report_dir / "history").mkdir(parents=True)
    (report_dir / "history" / "history.json").write_text(
        json.dumps({"h0": {"items": [{"status": "failed"}, {"status": "passed"}]}}),
        encoding="utf-8",
    )
    off = AIClient(provider=NullProvider("off"))

    local, outcome, path = ReportAssistant(off, tmp_path / "out").summarize(results, report_dir)

    assert len(local.groups) == 1  # both failures share one signature
    assert local.groups[0].history == "flaky"  # failed before and passed before
    assert not outcome.ok
    text = path.read_text(encoding="utf-8")
    assert "Failure groups (computed, no AI)" in text
    assert "AI narrative not available: off" in text


def test_run_summary_adds_ai_narrative(tmp_path: Path) -> None:
    results = _allure_results(tmp_path / "res", ["AssertionError: x"])
    narrative = ExecutionSummary(
        headline="1 product defect",
        health="amber",
        key_findings=["price bug"],
        group_comments=[],
        next_steps=["fix PATCH"],
    )
    ai, provider = _ai({ExecutionSummary: narrative}, tmp_path)

    _, outcome, path = ReportAssistant(ai, tmp_path / "out").summarize(results, tmp_path / "none")

    assert outcome.ok
    assert path.read_text(encoding="utf-8").startswith("# 1 product defect")
    assert '"history": "new"' in provider.requests[0].prompt
