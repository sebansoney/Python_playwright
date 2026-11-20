"""Final redaction pass over Allure result files (defence in depth).

Attachments we create and captured logs are already redacted. But Allure also stores
test *names*, *parameters* and failure *messages/traces* verbatim - e.g. a test
parametrized with a token, or an assertion message that prints one. After all workers
have finished, the main process rewrites every result/container JSON through the
redactor so nothing secret reaches the HTML report.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from framework.core.redaction import Redactor, get_redactor


def _sanitize(node: Any, redactor: Redactor) -> Any:
    if isinstance(node, str):
        return redactor.redact_text(node)
    if isinstance(node, list):
        return [_sanitize(item, redactor) for item in node]
    if isinstance(node, dict):
        # Allure parameter: {"name": "password", "value": "..."} -> mask by parameter name
        is_parameter = set(node) >= {"name", "value"} and isinstance(node.get("name"), str)
        if is_parameter and redactor.is_sensitive_key(node["name"]):
            return {**node, "value": redactor.mask}
        return {key: _sanitize(value, redactor) for key, value in node.items()}
    return node


def sanitize_results(results_dir: Path) -> int:
    """Redact all *-result.json / *-container.json files in place. Returns files changed."""
    redactor = get_redactor()
    changed = 0
    for path in list(results_dir.glob("*-result.json")) + list(
        results_dir.glob("*-container.json")
    ):
        try:
            original = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        cleaned = _sanitize(original, redactor)
        if cleaned != original:
            path.write_text(json.dumps(cleaned, ensure_ascii=False), encoding="utf-8")
            changed += 1
    return changed
