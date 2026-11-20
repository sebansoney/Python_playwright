"""Live smoke test of the Claude provider - makes REAL, billed API calls.

Skipped unless BOTH are set:  FW_AI_LIVE=1  and  ANTHROPIC_API_KEY.
Run:  FW_AI_LIVE=1 uv run pytest tests/ai_live -m ai_live
Uses effort "low" and a tiny schema to keep the cost to a fraction of a cent.
"""

import os

import pytest
from pydantic import BaseModel

from config.settings import Settings
from framework.ai.client import AIClient
from framework.ai.providers.claude import ClaudeProvider

pytestmark = [
    pytest.mark.ai_live,
    pytest.mark.skipif(
        os.environ.get("FW_AI_LIVE") != "1", reason="live AI tests are opt-in (FW_AI_LIVE=1)"
    ),
]


class Verdict(BaseModel):
    category: str
    one_line_reason: str


def test_claude_returns_structured_output_through_the_gate(settings: Settings, tmp_path) -> None:  # type: ignore[no-untyped-def]
    if not settings.anthropic_api_key:
        pytest.skip("ANTHROPIC_API_KEY not set")
    provider = ClaudeProvider(
        api_key=settings.anthropic_api_key.get_secret_value(),
        model=settings.ai.model,
        effort="low",
        max_tokens=2000,
    )
    ai = AIClient(provider=provider, max_calls=1, audit_dir=tmp_path)

    outcome = ai.ask(
        system="Classify the test failure as product_defect, test_defect or environment.",
        prompt="AssertionError: expected HTTP 200, got 404 for GET /api/v1/users/999999999 "
        "(the test deliberately requests an id that does not exist). User: qa@example.test",
        schema=Verdict,
        purpose="live-smoke",
    )

    assert outcome.ok, outcome.message
    assert outcome.value is not None
    assert outcome.value.category in {"product_defect", "test_defect", "environment"}
    sent = next(tmp_path.iterdir()).read_text(encoding="utf-8")
    assert "qa@example.test" not in sent  # email masked before it left the machine
    assert outcome.usage is not None
    assert outcome.usage.output_tokens > 0
