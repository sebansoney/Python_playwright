"""AI Test Data Generator: validation rules -> valid / invalid / boundary data sets.

Generated data is a DRAFT (``ai_drafts/data``). Values that must be unique carry a
``{unique}`` placeholder which ``materialize`` replaces with a fresh token, so the same
file can be used many times and in parallel runs.
"""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, Field

from framework.ai.client import AIClient, AIOutcome
from framework.ai.services.common import load_prompt, timestamp, write_draft
from framework.data.factories import token

# Rules as documented in docs/sample_application.md - the single source for the AI prompt.
ENTITY_RULES: dict[str, str] = {
    "product": (
        "name: string, required, 2-80 chars\n"
        "sku: string, required, unique, 3-20 chars of A-Z, 0-9 and '-', stored upper-case\n"
        "category: required, one of Books, Clothing, Electronics, Home, Sports, Toys\n"
        "price: number, required, > 0 and <= 100000, at most 2 decimal places\n"
        "stock: integer, optional (default 0), 0-100000\n"
        "description: string, optional, max 500 chars"
    ),
    "user": (
        "full_name: string, required, 2-60 chars\n"
        "email: required, unique, valid email format, max 120 chars, stored lower-case\n"
        "password: required, 8-64 chars, at least one letter and one digit\n"
        "role: optional, one of admin, user (default user)\n"
        "phone: optional, '+' then digits/spaces/dashes, 7-20 chars"
    ),
}


class FieldValue(BaseModel):
    field: str
    value: str = Field(description="JSON-encoded value, e.g. '\"Desk Lamp\"', '12.5', 'null'")


class ValidRecord(BaseModel):
    fields: list[FieldValue]
    note: str


class InvalidRecord(BaseModel):
    fields: list[FieldValue]
    invalid_field: str
    rule_broken: str
    expected_message: str = Field(description="Expected validation message if known, else empty")


class BoundaryRecord(BaseModel):
    fields: list[FieldValue]
    field: str
    boundary: str = Field(description="e.g. 'max length 80', 'just above max price'")
    expected_valid: bool


class GeneratedData(BaseModel):
    entity: str
    valid: list[ValidRecord]
    invalid: list[InvalidRecord]
    boundary: list[BoundaryRecord]


def materialize(fields: list[FieldValue]) -> dict[str, object]:
    """Turn a generated record into a payload dict, filling {unique} placeholders."""
    unique = token().upper()
    payload: dict[str, object] = {}
    for f in fields:
        raw = f.value.replace("{unique}", unique)
        try:
            payload[f.field] = json.loads(raw)
        except ValueError:
            payload[f.field] = raw
    return payload


class TestDataGenerator:
    __test__ = False  # not a pytest test class (name starts with 'Test')

    def __init__(self, ai: AIClient, drafts_dir: Path) -> None:
        self.ai = ai
        self.drafts_dir = drafts_dir

    def generate(self, entity: str, count: int = 5) -> tuple[AIOutcome[GeneratedData], Path | None]:
        if entity not in ENTITY_RULES:
            raise ValueError(f"Unknown entity '{entity}'. Known: {sorted(ENTITY_RULES)}")
        outcome = self.ai.ask(
            system=load_prompt("data_generator"),
            prompt=(
                f"<entity>{entity}</entity>\n<rules>\n{ENTITY_RULES[entity]}\n</rules>\n"
                f"<amounts>about {count} valid records, one invalid record per rule, and "
                f"boundary records for every limit</amounts>"
            ),
            schema=GeneratedData,
            purpose=f"test-data-{entity}",
        )
        if not (outcome.ok and outcome.value):
            return outcome, None
        path = write_draft(
            self.drafts_dir / "data",
            f"{entity}_data_{timestamp()}.json",
            outcome.value.model_dump_json(indent=2),
        )
        return outcome, path
