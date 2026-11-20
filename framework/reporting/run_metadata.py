"""Allure run metadata: environment.properties and categories.json.

Categories group failures on the report's "Categories" tab so a reader can tell
product defects from environment problems at a glance:

* Allure marks a test **failed** when an ``AssertionError`` is raised (the product
  did not behave as expected) and **broken** for any other exception (the test or
  its environment could not run properly).
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path

CATEGORIES: list[dict[str, object]] = [
    {
        "name": "Environment / infrastructure problems",
        "description": "Application unreachable, setup API failed, browser crashed.",
        "matchedStatuses": ["broken", "failed"],
        "traceRegex": (
            r"(?s).*(AppNotReachableError|BackdoorError|AuthenticationError|ConnectError|"
            r"ConnectTimeout|TargetClosedError|Browser has been closed).*"
        ),
    },
    {
        "name": "UI element not found / timeout",
        "description": (
            "A Playwright action timed out: missing element, changed locator or slow page."
        ),
        "matchedStatuses": ["broken"],
        "traceRegex": r"(?s).*playwright\._impl\._errors\.TimeoutError.*",
    },
    {
        "name": "Product defects (assertion failed)",
        "description": "The application behaved differently from the expected result.",
        "matchedStatuses": ["failed"],
    },
    {
        "name": "Test defects (broken test code)",
        "description": "Unexpected exception in test or framework code.",
        "matchedStatuses": ["broken"],
    },
    {"name": "Skipped", "matchedStatuses": ["skipped"]},
]


def write_categories(results_dir: Path) -> Path:
    results_dir.mkdir(parents=True, exist_ok=True)
    path = results_dir / "categories.json"
    path.write_text(json.dumps(CATEGORIES, indent=2), encoding="utf-8")
    return path


def write_environment(results_dir: Path, info: Mapping[str, object]) -> Path:
    """Allure's 'Environment' widget. Keys must not contain '=' or ':'; values are
    single-line. Never put secrets here."""
    results_dir.mkdir(parents=True, exist_ok=True)
    path = results_dir / "environment.properties"
    lines = []
    for key, value in info.items():
        safe_key = str(key).replace(" ", ".").replace("=", "_").replace(":", "_")
        safe_value = str(value).replace("\n", " ").replace("\\", "/")
        lines.append(f"{safe_key}={safe_value}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path
