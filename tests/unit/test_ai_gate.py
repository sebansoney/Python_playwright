"""Self-tests for the AI safety gate, factory and Claude provider wiring (no network)."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from pydantic import BaseModel

from config.settings import load_settings
from framework.ai.client import AIClient
from framework.ai.errors import AIError, AIRefusalError, AIUnavailableError
from framework.ai.factory import build_provider
from framework.ai.providers.base import ImageInput, LLMRequest, LLMUsage
from framework.ai.providers.null import NullProvider
from framework.core.redaction import get_redactor

JWT = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJhZG1pbiJ9.c2lnbmF0dXJlLXZhbHVl"


class Answer(BaseModel):
    text: str


class FakeProvider:
    name = "fake"
    model = "fake-model"

    def __init__(self, error: Exception | None = None) -> None:
        self.requests: list[LLMRequest] = []
        self.error = error

    def generate(self, request: LLMRequest, schema: type[Any]) -> tuple[Any, LLMUsage]:
        self.requests.append(request)
        if self.error:
            raise self.error
        return schema(text="ok"), LLMUsage(input_tokens=10, output_tokens=5, model="fake-model")


def _client(tmp_path: Path, provider: Any, **kwargs: Any) -> AIClient:
    return AIClient(provider=provider, audit_dir=tmp_path / "requests", **kwargs)


def test_gate_redacts_secrets_and_emails_before_sending(tmp_path: Path) -> None:
    get_redactor().register_secret("Very-Secret-Pw1")
    fake = FakeProvider()
    ai = _client(tmp_path, fake)

    outcome = ai.ask(
        system="system with Very-Secret-Pw1",
        prompt=f"user ann@example.test, password=Very-Secret-Pw1, token {JWT}, "
        "Bearer abcdefghijklmn",
        schema=Answer,
        purpose="unit",
    )

    assert outcome.ok
    assert outcome.value == Answer(text="ok")
    sent = fake.requests[0]
    for leaked in ("Very-Secret-Pw1", "ann@example.test", JWT, "abcdefghijklmn"):
        assert leaked not in sent.prompt + sent.system
    assert "<email>" in sent.prompt
    audit = next((tmp_path / "requests").iterdir()).read_text(encoding="utf-8")
    assert "Very-Secret-Pw1" not in audit
    assert "ann@example.test" not in audit
    assert "<email>" in audit  # the audit shows exactly what was sent


def test_screenshots_are_dropped_unless_explicitly_allowed(tmp_path: Path) -> None:
    image = (ImageInput("image/png", b"\x89PNG fake", "shot"),)
    fake = FakeProvider()

    _client(tmp_path, fake, send_images=False).ask(
        system="s", prompt="p", schema=Answer, purpose="u", images=image
    )
    _client(tmp_path, fake, send_images=True).ask(
        system="s", prompt="p", schema=Answer, purpose="u", images=image
    )

    assert fake.requests[0].images == ()
    assert fake.requests[1].images == image


def test_call_budget_is_enforced(tmp_path: Path) -> None:
    fake = FakeProvider()
    ai = _client(tmp_path, fake, max_calls=2)

    results = [ai.ask(system="s", prompt="p", schema=Answer, purpose="u") for _ in range(3)]

    assert [r.ok for r in results] == [True, True, False]
    assert "budget exhausted" in results[2].message
    assert len(fake.requests) == 2
    assert ai.total_usage.input_tokens == 20


@pytest.mark.parametrize(
    "error", [AIUnavailableError("down"), AIRefusalError("declined"), AIError("bad")]
)
def test_provider_errors_never_raise(tmp_path: Path, error: AIError) -> None:
    outcome = _client(tmp_path, FakeProvider(error)).ask(
        system="s", prompt="p", schema=Answer, purpose="u"
    )

    assert not outcome.ok
    assert outcome.message == str(error)


def test_disabled_ai_is_a_harmless_no_op(tmp_path: Path) -> None:
    ai = _client(tmp_path, NullProvider("off for test"))

    outcome = ai.ask(system="s", prompt="p", schema=Answer, purpose="u")

    assert not ai.enabled
    assert (outcome.ok, outcome.message) == (False, "off for test")
    assert not (tmp_path / "requests").exists()  # nothing was "sent"


@pytest.fixture
def _no_env(monkeypatch: pytest.MonkeyPatch) -> None:
    import os

    for key in list(os.environ):
        if key.startswith("FW_AI") or key == "ANTHROPIC_API_KEY":
            monkeypatch.delenv(key, raising=False)


@pytest.mark.usefixtures("_no_env")
def test_factory_falls_back_to_null_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    assert "disabled" in build_provider(load_settings("local", env_file=None)).reason  # type: ignore[union-attr]

    monkeypatch.setenv("FW_AI__ENABLED", "true")
    no_key = build_provider(load_settings("local", env_file=None))
    assert isinstance(no_key, NullProvider)
    assert "ANTHROPIC_API_KEY" in no_key.reason

    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-0000000000000000")
    provider = build_provider(load_settings("local", env_file=None))
    assert provider.name == "claude"
    assert provider.model == "claude-opus-5-5"  # type: ignore[attr-defined]


# ------------------------------------------------------------- Claude wiring
def _claude(model: str = "claude-opus-5-5") -> Any:
    from framework.ai.providers.claude import ClaudeProvider

    return ClaudeProvider(api_key="sk-ant-test-0000000000000000", model=model, effort="high")


def _fake_parse(provider: Any, stop_reason: str = "end_turn") -> dict[str, Any]:
    captured: dict[str, Any] = {}

    def parse(**kwargs: Any) -> Any:
        captured.update(kwargs)
        return SimpleNamespace(
            stop_reason=stop_reason,
            stop_details=SimpleNamespace(category="cyber"),
            parsed_output=Answer(text="parsed") if stop_reason == "end_turn" else None,
            usage=SimpleNamespace(
                input_tokens=100,
                output_tokens=20,
                cache_read_input_tokens=80,
                cache_creation_input_tokens=0,
            ),
            model="claude-opus-5-5",
        )

    provider._client = SimpleNamespace(beta=SimpleNamespace(messages=SimpleNamespace(parse=parse)))
    return captured


def test_claude_request_shape() -> None:
    provider = _claude()
    captured = _fake_parse(provider)
    request = LLMRequest(
        system="SYS", prompt="PROMPT", images=(ImageInput("image/png", b"png", "shot"),)
    )

    value, usage = provider.generate(request, Answer)

    assert value == Answer(text="parsed")
    assert (usage.input_tokens, usage.cache_read_tokens) == (100, 80)
    assert captured["model"] == "claude-opus-5-5"
    assert captured["output_format"] is Answer
    assert captured["output_config"] == {"effort": "high"}
    assert captured["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert captured["fallbacks"] == "default"
    assert captured["betas"] == ["server-side-fallback-2026-07-01"]
    content = captured["messages"][0]["content"]
    assert [b["type"] for b in content] == ["text", "image", "text"]
    assert content[1]["source"] == {"type": "base64", "media_type": "image/png", "data": "cG5n"}


def test_claude_fallback_only_for_supported_models() -> None:
    provider = _claude("claude-haiku-5-5")
    captured = _fake_parse(provider)

    provider.generate(LLMRequest(system="s", prompt="p"), Answer)

    assert "fallbacks" not in captured
    assert "betas" not in captured


@pytest.mark.parametrize(("stop", "error"), [("refusal", AIRefusalError), ("max_tokens", AIError)])
def test_claude_stop_reasons_map_to_errors(stop: str, error: type[Exception]) -> None:
    provider = _claude()
    _fake_parse(provider, stop_reason=stop)

    with pytest.raises(error):
        provider.generate(LLMRequest(system="s", prompt="p"), Answer)


def test_claude_connection_problems_become_unavailable() -> None:
    import anthropic
    import httpx2

    provider = _claude()

    def parse(**_: Any) -> Any:
        raise anthropic.APIConnectionError(request=httpx2.Request("POST", "https://api.example"))

    provider._client = SimpleNamespace(beta=SimpleNamespace(messages=SimpleNamespace(parse=parse)))

    with pytest.raises(AIUnavailableError, match="not reachable"):
        provider.generate(LLMRequest(system="s", prompt="p"), Answer)
