"""AI Locator Assistant: broken locator + DOM -> ranked, VERIFIED alternatives.

Candidates are structured (strategy + value), never code strings, so they can be turned
into Playwright locators without ``eval`` and checked against the live page: a
suggestion that matches 0 or several elements is reported as such, not trusted.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from framework.ai.client import AIClient, AIOutcome
from framework.ai.services.common import load_prompt, timestamp, write_report


class LocatorCandidate(BaseModel):
    strategy: Literal["role", "label", "placeholder", "text", "test_id", "title", "css"]
    value: str = Field(
        description="role name for 'role' (e.g. button); otherwise the text/id/selector"
    )
    name: str = Field(description="accessible name for 'role'; empty otherwise")
    exact: bool
    rationale: str
    stability: Literal["high", "medium", "low"]

    def as_code(self) -> str:
        exact = ", exact=True" if self.exact else ""
        match self.strategy:
            case "role":
                name = f', name="{self.name}"' if self.name else ""
                return f'page.get_by_role("{self.value}"{name}{exact})'
            case "css":
                return f'page.locator("{self.value}")'
            case "test_id":
                return f'page.get_by_test_id("{self.value}")'
            case _:
                return f'page.get_by_{self.strategy}("{self.value}"{exact})'

    def build(self, page: Any) -> Any:
        """Create the Playwright locator (works for Page, Frame or Locator roots)."""
        exact = {"exact": True} if self.exact else {}
        if self.strategy == "role":
            return page.get_by_role(
                self.value, **({"name": self.name} if self.name else {}), **exact
            )
        if self.strategy == "css":
            return page.locator(self.value)
        if self.strategy == "test_id":
            return page.get_by_test_id(self.value)
        return getattr(page, f"get_by_{self.strategy}")(self.value, **exact)


class LocatorSuggestions(BaseModel):
    diagnosis: str
    candidates: list[LocatorCandidate]


class VerifiedCandidate(BaseModel):
    code: str
    matches: int
    stability: str
    rationale: str


class LocatorAssistant:
    def __init__(self, ai: AIClient, out_dir: Path) -> None:
        self.ai = ai
        self.out_dir = out_dir

    def suggest(self, failed_locator: str, intent: str, html: str) -> AIOutcome[LocatorSuggestions]:
        return self.ai.ask(
            system=load_prompt("locator_assistant"),
            prompt=(
                f"<failed_locator>{failed_locator}</failed_locator>\n<intent>{intent}</intent>\n"
                f"<html>\n{html[:60_000]}\n</html>"
            ),
            schema=LocatorSuggestions,
            purpose="locator-suggestions",
        )

    @staticmethod
    def verify(page: Any, suggestions: LocatorSuggestions) -> list[VerifiedCandidate]:
        """Count matches on the live page; unique matches first, then by stability."""
        order = {"high": 0, "medium": 1, "low": 2}
        verified = []
        for c in suggestions.candidates:
            try:
                count = c.build(page).count()
            except Exception:  # invalid role/selector from the model
                count = -1
            verified.append(
                VerifiedCandidate(
                    code=c.as_code(), matches=count, stability=c.stability, rationale=c.rationale
                )
            )
        return sorted(verified, key=lambda v: (v.matches != 1, order.get(v.stability, 3)))

    def suggest_for_page(
        self, page: Any, failed_locator: str, intent: str
    ) -> tuple[AIOutcome[LocatorSuggestions], list[VerifiedCandidate]]:
        """Use inside a test/debug session: reads the live DOM, asks, then verifies."""
        outcome = self.suggest(failed_locator, intent, page.content())
        verified = self.verify(page, outcome.value) if outcome.ok and outcome.value else []
        if outcome.ok and outcome.value:
            lines = [
                "# Locator suggestions\n",
                f"**Failed:** `{failed_locator}`  \n**Intent:** {intent}\n",
                f"**Diagnosis:** {outcome.value.diagnosis}\n",
                "| Locator | Matches | Stability | Why |",
                "|---|---|---|---|",
            ]
            lines += [
                f"| `{v.code}` | {v.matches} | {v.stability} | {v.rationale} |" for v in verified
            ]
            write_report(
                self.out_dir,
                f"locator_suggestions_{timestamp()}",
                "\n".join(lines) + "\n",
                outcome.value,
            )
        return outcome, verified
