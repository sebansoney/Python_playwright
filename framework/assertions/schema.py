"""JSON Schema validation against the contract files in framework/api/schemas.

Schemas reference each other by relative ``$ref`` (e.g. user_page.json -> user.json);
all files are loaded into one registry so references resolve offline.
"""

from __future__ import annotations

import json
from functools import cache
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource

from framework.core.paths import SCHEMAS_DIR


@cache
def _registry() -> Registry:
    resources = []
    for path in SCHEMAS_DIR.glob("*.json"):
        contents = json.loads(path.read_text(encoding="utf-8"))
        resources.append((contents["$id"], Resource.from_contents(contents)))
    return Registry().with_resources(resources)


@cache
def _validator(name: str) -> Draft202012Validator:
    path = SCHEMAS_DIR / f"{name}.json"
    if not path.exists():
        available = sorted(p.stem for p in SCHEMAS_DIR.glob("*.json"))
        raise FileNotFoundError(f"No schema '{name}'. Available: {available}")
    schema = json.loads(path.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema, registry=_registry(), format_checker=FormatChecker())


def schema_errors(instance: Any, name: str) -> list[str]:
    """All violations as readable lines, e.g. ``items/0/price: -1 is less than ...``."""
    errors = sorted(_validator(name).iter_errors(instance), key=lambda e: list(e.absolute_path))
    return [f"{'/'.join(map(str, e.absolute_path)) or '<root>'}: {e.message}" for e in errors]


def validate_schema(instance: Any, name: str) -> None:
    __tracebackhide__ = True
    problems = schema_errors(instance, name)
    if problems:
        raise AssertionError(
            f"Response does not match schema '{name}' ({len(problems)} problem(s)):\n  - "
            + "\n  - ".join(problems)
        )
