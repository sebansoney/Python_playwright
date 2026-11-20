"""AI Reporting Assistant.

The deterministic part runs WITHOUT AI and is always produced:
  * statistics from Allure results,
  * failures grouped by a normalised error signature (ids, numbers, uuids, quotes removed),
  * recurring / flaky detection from the Allure report history of previous runs.
The AI only adds the narrative (headline, health, findings, owners, next steps).
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from framework.ai.client import AIClient, AIOutcome
from framework.ai.evidence import AllureResults, RunResults
from framework.ai.services.common import bullet, load_prompt, timestamp, write_report

_NORMALISERS = [
    (re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f-]{27,}", re.I), "<uuid>"),
    (re.compile(r"\b[0-9a-f]{32}\b", re.I), "<hex>"),
    (re.compile(r"\bAT-[0-9A-F]{6,}\b"), "<sku>"),
    (re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.]+\b"), "<email>"),
    (re.compile(r"'[^']*'|\"[^\"]*\""), "<str>"),
    (re.compile(r"\b\d+(\.\d+)?\b"), "<n>"),
]


def signature(message: str) -> str:
    first = (
        (message or "").strip().splitlines()[0] if message and message.strip() else "<no message>"
    )
    for pattern, repl in _NORMALISERS:
        first = pattern.sub(repl, first)
    return first[:200]


@dataclass
class FailureGroup:
    id: str
    signature: str
    tests: list[str]
    history: Literal["new", "recurring", "flaky"] = "new"


@dataclass
class LocalSummary:
    run: RunResults
    groups: list[FailureGroup] = field(default_factory=list)


def _history(report_dir: Path) -> dict[str, list[str]]:
    """historyId -> previous statuses (newest first) from an earlier generated report."""
    path = report_dir / "history" / "history.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return {
        hid: [i.get("status", "") for i in entry.get("items", [])] for hid, entry in data.items()
    }


def build_local_summary(results_dir: Path, report_dir: Path) -> LocalSummary:
    run = AllureResults(results_dir).load()
    history = _history(report_dir)
    groups: dict[str, FailureGroup] = {}
    for ev in run.failures:
        sig = signature(ev.message)
        gid = "G" + hashlib.sha1(sig.encode()).hexdigest()[:6]
        group = groups.setdefault(gid, FailureGroup(gid, sig, []))
        group.tests.append(ev.full_name)
        past = history.get(ev.history_id, [])
        if any(s in ("failed", "broken") for s in past) and group.history != "flaky":
            group.history = "flaky" if "passed" in past else "recurring"
    return LocalSummary(run, sorted(groups.values(), key=lambda g: -len(g.tests)))


class GroupComment(BaseModel):
    group_id: str
    likely_cause: str
    suggested_owner: Literal["dev", "qa", "devops", "unknown"]


class ExecutionSummary(BaseModel):
    headline: str
    health: Literal["green", "amber", "red"]
    key_findings: list[str]
    group_comments: list[GroupComment]
    next_steps: list[str]


def render_local(local: LocalSummary) -> str:
    r = local.run
    stats = " · ".join(f"{k}: {v}" for k, v in sorted(r.by_status.items())) or "no results"
    lines = [
        "# Test run summary",
        f"\n**Total:** {r.total} · {stats} · **Duration:** {r.duration_ms / 1000:.1f} s",
        "\n**Environment:** "
        + (
            ", ".join(
                f"{k}={v}"
                for k, v in r.environment.items()
                if k in ("Environment", "Browsers", "Parallel.workers")
            )
            or "-"
        ),
        "\n## Failure groups (computed, no AI)\n",
    ]
    if not local.groups:
        lines.append("No failures.")
    for g in local.groups:
        lines.append(
            f"### {g.id} - {g.history} - {len(g.tests)} test(s)\n"
            f"`{g.signature}`\n\n{bullet(g.tests)}\n"
        )
    return "\n".join(lines) + "\n"


class ReportAssistant:
    def __init__(self, ai: AIClient, out_dir: Path) -> None:
        self.ai = ai
        self.out_dir = out_dir

    def summarize(
        self, results_dir: Path, report_dir: Path
    ) -> tuple[LocalSummary, AIOutcome[ExecutionSummary], Path]:
        local = build_local_summary(results_dir, report_dir)
        markdown = render_local(local)
        outcome: AIOutcome[ExecutionSummary] = AIOutcome(
            ok=False, message="no failures - AI not needed"
        )
        if local.groups:  # a green run needs no narrative - don't spend tokens on it
            payload = {
                "stats": local.run.by_status,
                "total": local.run.total,
                "duration_s": round(local.run.duration_ms / 1000, 1),
                "groups": [
                    {"id": g.id, "signature": g.signature, "history": g.history, "tests": g.tests}
                    for g in local.groups
                ],
            }
            outcome = self.ai.ask(
                system=load_prompt("report_assistant"),
                prompt=f"<run>\n{json.dumps(payload, indent=2)}\n</run>",
                schema=ExecutionSummary,
                purpose="run-summary",
            )
        if outcome.ok and outcome.value:
            s = outcome.value
            comments = "\n".join(
                f"- **{c.group_id}** ({c.suggested_owner}): {c.likely_cause}"
                for c in s.group_comments
            )
            markdown = (
                f"# {s.headline}\n\n**Health:** {s.health.upper()}  \n"
                "> AI-written narrative; numbers and groups below are computed.\n\n"
                f"## Key findings\n{bullet(s.key_findings)}\n\n"
                f"## Failure groups - likely causes\n{comments or '- (none)'}\n\n"
                f"## Next steps\n{bullet(s.next_steps)}\n\n---\n\n" + markdown
            )
        else:
            markdown += f"\n_AI narrative not available: {outcome.message}_\n"
        path = write_report(self.out_dir, f"run_summary_{timestamp()}", markdown, outcome.value)
        return local, outcome, path
