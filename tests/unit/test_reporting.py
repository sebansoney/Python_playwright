"""Self-tests for the reporting helpers (no Allure run needed)."""

import json
from pathlib import Path

from framework.core.redaction import get_redactor
from framework.reporting.run_metadata import CATEGORIES, write_categories, write_environment
from framework.reporting.sanitize import sanitize_results

JWT = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJhZG1pbiJ9.c2lnbmF0dXJlLXZhbHVl"


def test_sanitize_redacts_names_parameters_and_messages(tmp_path: Path) -> None:
    get_redactor().register_secret("Real-Pa55word")
    result = {
        "name": f"test_x[{JWT}]",
        "status": "failed",
        "statusDetails": {"message": "AssertionError: login with Real-Pa55word failed"},
        "parameters": [
            {"name": "password", "value": "anything"},
            {"name": "browser_name", "value": "chromium"},
        ],
        "steps": [{"name": "Authorization: Bearer abcdefghijklmnop", "status": "passed"}],
    }
    file = tmp_path / "abc-result.json"
    file.write_text(json.dumps(result), encoding="utf-8")
    untouched = tmp_path / "def-result.json"
    untouched.write_text(json.dumps({"name": "test_y", "status": "passed"}), encoding="utf-8")

    assert sanitize_results(tmp_path) == 1

    text = file.read_text(encoding="utf-8")
    assert JWT not in text
    assert "Real-Pa55word" not in text
    assert "abcdefghijklmnop" not in text
    cleaned = json.loads(text)
    assert cleaned["parameters"][0]["value"] == "***REDACTED***"
    assert cleaned["parameters"][1]["value"] == "chromium"  # non-secret params untouched


def test_environment_properties_are_single_line_key_values(tmp_path: Path) -> None:
    path = write_environment(tmp_path, {"Base URL": "http://x:1", "Command": "pytest\n-k a"})

    lines = path.read_text(encoding="utf-8").splitlines()
    assert lines == ["Base.URL=http://x:1", "Command=pytest -k a"]


def test_categories_file_is_valid_and_ordered(tmp_path: Path) -> None:
    data = json.loads(write_categories(tmp_path).read_text(encoding="utf-8"))

    assert data == CATEGORIES
    # Specific categories must come before the generic catch-alls (first match wins).
    names = [c["name"] for c in data]
    assert names.index("Environment / infrastructure problems") < names.index(
        "Product defects (assertion failed)"
    )
    assert names.index("UI element not found / timeout") < names.index(
        "Test defects (broken test code)"
    )
