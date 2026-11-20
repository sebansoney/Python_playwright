"""The AI CLI must work - and explain itself - when AI is off."""

import os

import pytest

from framework.ai.cli import main


@pytest.fixture(autouse=True)
def _ai_off(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in list(os.environ):
        if key.startswith("FW_AI"):
            monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("FW_AI__ENABLED", "false")


def test_status_reports_configuration_without_secrets(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["status"]) == 0

    out = capsys.readouterr().out
    assert "model=claude-opus-5-5" in out
    assert "AI is off" in out
    assert "sk-ant" not in out


@pytest.mark.parametrize(
    "argv",
    [
        ["generate-data", "--entity", "product"],
        ["analyze-failures", "--max", "1"],
        ["suggest-locators", "--html", "x.html", "--locator", "x", "--intent", "y"],
    ],
)
def test_ai_commands_exit_cleanly_when_ai_is_off(
    argv: list[str], capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(argv) == 0
    assert "AI is off" in capsys.readouterr().out
