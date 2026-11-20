"""Read test evidence from Allure results - locally, before anything goes to an AI.

The AI never sees raw files. This module extracts the useful parts, keeps them small,
and the AIClient redacts them again before sending:
  * failure message + trimmed stack trace, step names with status,
  * attachments we created (API exchanges, captured log, DOM snapshot) - text only,
  * Playwright traces: only console errors and failed (4xx/5xx) network requests are
    extracted; the raw trace (cookies, typed values) never leaves the machine,
  * screenshots are passed as bytes, and the AIClient decides whether to send them.
"""

from __future__ import annotations

import contextlib
import json
import re
import zipfile
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_TEXT_LIMIT = 6_000
_STATUS_MEANING = {"failed": "assertion failed", "broken": "unexpected exception"}
_TRACE_LIMIT = 4_000


def _trim(text: str, limit: int = _TEXT_LIMIT) -> str:
    return (
        text
        if len(text) <= limit
        else text[:limit] + f"\n... <truncated {len(text) - limit} chars>"
    )


@dataclass
class FailureEvidence:
    name: str
    full_name: str
    status: str  # failed | broken
    message: str
    trace: str
    labels: dict[str, str]
    steps: list[str]
    api_exchanges: str = ""
    log: str = ""
    dom_snapshot: str = ""
    dom_url: str = ""
    trace_findings: list[str] = field(default_factory=list)
    screenshot: bytes | None = None
    history_id: str = ""

    def to_prompt(self) -> str:
        parts = [
            f"Test: {self.full_name}",
            f"Status: {self.status} ({_STATUS_MEANING.get(self.status, 'unknown')})",
            "Labels: " + ", ".join(f"{k}={v}" for k, v in sorted(self.labels.items())),
            f"Message:\n{_trim(self.message, 2_000)}",
            f"Stack trace (trimmed):\n{_trim(self.trace, 3_000)}",
            "Steps:\n" + ("\n".join(self.steps) or "(none)"),
        ]
        if self.api_exchanges:
            parts.append(f"API exchanges:\n{_trim(self.api_exchanges)}")
        if self.trace_findings:
            parts.append(
                "Browser console errors / failed requests:\n" + "\n".join(self.trace_findings)
            )
        if self.log:
            parts.append(f"Captured log:\n{_trim(self.log, 3_000)}")
        if self.dom_snapshot:
            parts.append(f"DOM at failure ({self.dom_url}):\n{_trim(self.dom_snapshot, 8_000)}")
        return "\n\n".join(parts)


@dataclass
class RunResults:
    total: int
    by_status: dict[str, int]
    duration_ms: int
    failures: list[FailureEvidence]
    environment: dict[str, str]


def _walk_steps(steps: list[dict[str, Any]], depth: int = 0) -> list[str]:
    lines: list[str] = []
    for step in steps or []:
        lines.append(f"{'  ' * depth}- {step.get('name')} [{step.get('status')}]")
        lines.extend(_walk_steps(step.get("steps", []), depth + 1))
    return lines


def _attachments(result: dict[str, Any]) -> list[dict[str, Any]]:
    found = list(result.get("attachments", []))
    stack = list(result.get("steps", []))
    while stack:
        step = stack.pop()
        found.extend(step.get("attachments", []))
        stack.extend(step.get("steps", []))
    return found


def extract_trace_findings(trace_zip: Path, limit: int = 15) -> list[str]:
    """Console errors and failed network requests from a Playwright trace (best effort)."""
    findings: list[str] = []
    try:
        with zipfile.ZipFile(trace_zip) as archive:
            for member in archive.namelist():
                if not member.endswith((".trace", ".network")):
                    continue
                for raw in archive.read(member).decode("utf-8", "replace").splitlines():
                    try:
                        event = json.loads(raw)
                    except ValueError:
                        continue
                    findings.extend(_finding(event))
    except (OSError, zipfile.BadZipFile):
        return []
    unique = list(dict.fromkeys(findings))
    return [_trim(f, 300) for f in unique[:limit]]


def _finding(event: dict[str, Any]) -> list[str]:
    kind = event.get("type")
    if kind == "console" and event.get("messageType") in ("error", "warning"):
        return [f"console.{event.get('messageType')}: {event.get('text', '')}"]
    if kind == "event" and event.get("method") == "pageError":
        return [f"page error: {json.dumps(event.get('params', {}))[:250]}"]
    if kind == "resource-snapshot":
        snapshot = event.get("snapshot", {})
        status = snapshot.get("response", {}).get("status", 0)
        if isinstance(status, int) and status >= 400:
            request = snapshot.get("request", {})
            return [f"HTTP {status} {request.get('method', '')} {request.get('url', '')}"]
    return []


class AllureResults:
    def __init__(self, results_dir: Path) -> None:
        self.dir = results_dir

    def _results(self) -> list[dict[str, Any]]:
        if not self.dir.is_dir():
            return []
        out = []
        for path in self.dir.glob("*-result.json"):
            try:
                out.append(json.loads(path.read_text(encoding="utf-8")))
            except (OSError, ValueError):
                continue
        return out

    def _read_text(self, source: str) -> str:
        try:
            return (self.dir / source).read_text(encoding="utf-8", errors="replace")
        except OSError:
            return ""

    def environment(self) -> dict[str, str]:
        path = self.dir / "environment.properties"
        if not path.exists():
            return {}
        pairs = (
            line.split("=", 1)
            for line in path.read_text(encoding="utf-8").splitlines()
            if "=" in line
        )
        return {k: v for k, v in pairs}

    def load(self) -> RunResults:
        results = self._results()
        statuses = Counter(r.get("status", "unknown") for r in results)
        starts = [r["start"] for r in results if "start" in r]
        stops = [r["stop"] for r in results if "stop" in r]
        duration = (max(stops) - min(starts)) if starts and stops else 0
        failures = [self._evidence(r) for r in results if r.get("status") in ("failed", "broken")]
        failures.sort(key=lambda f: f.full_name)
        return RunResults(len(results), dict(statuses), duration, failures, self.environment())

    def _evidence(self, result: dict[str, Any]) -> FailureEvidence:
        details = result.get("statusDetails", {})
        ev = FailureEvidence(
            name=result.get("name", ""),
            full_name=result.get("fullName", result.get("name", "")),
            status=result.get("status", ""),
            message=details.get("message", ""),
            trace=details.get("trace", ""),
            labels={
                lbl["name"]: lbl["value"]
                for lbl in result.get("labels", [])
                if lbl.get("name") in ("epic", "feature", "severity", "suite")
            },
            steps=_walk_steps(result.get("steps", [])),
            history_id=result.get("historyId", ""),
        )
        for att in _attachments(result):
            name, source = att.get("name", ""), att.get("source", "")
            if name.startswith("API exchanges"):
                ev.api_exchanges = self._read_text(source)
            elif name == "log":
                ev.log = self._read_text(source)
            elif name.startswith("DOM snapshot"):
                ev.dom_snapshot = self._read_text(source)
                match = re.search(r" - (\S+)$", name)
                ev.dom_url = match.group(1) if match else ""
            elif name.startswith("Screenshot") and ev.screenshot is None:
                with contextlib.suppress(OSError):
                    ev.screenshot = (self.dir / source).read_bytes()
            elif source.endswith(".zip"):
                ev.trace_findings = extract_trace_findings(self.dir / source)
        return ev
