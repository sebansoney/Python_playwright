"""Turn pydantic validation errors into stable, human-friendly messages.

Used by the API (422 body) and by the web forms (inline errors), so tests can
assert on the same wording at both layers.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from pydantic import BaseModel, ValidationError

from sample_application.backend.schemas import PATTERN_MESSAGES

LABELS = {
    "email": "Email",
    "full_name": "Full name",
    "password": "Password",
    "new_password": "New password",
    "current_password": "Current password",
    "confirm_password": "Confirm password",
    "phone": "Phone",
    "role": "Role",
    "is_active": "Active",
    "name": "Name",
    "sku": "SKU",
    "category": "Category",
    "price": "Price",
    "stock": "Stock",
    "description": "Description",
    "min_price": "Minimum price",
    "max_price": "Maximum price",
    "page": "Page",
    "size": "Page size",
}


def _field_name(loc: Iterable[Any]) -> str:
    parts = [str(p) for p in loc if p not in ("body", "query", "path")]
    return ".".join(parts) or "body"


def _num(value: Any) -> Any:
    """Show limits like a human would: 0.0 -> 0, 100000.0 -> 100000, 0.5 stays 0.5."""
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return value


def friendly_message(error: Mapping[str, Any]) -> str:
    field = _field_name(error.get("loc", ()))
    leaf = field.split(".")[-1]
    label = LABELS.get(leaf, leaf.replace("_", " ").capitalize())
    etype: str = error.get("type", "")
    ctx: Mapping[str, Any] = error.get("ctx") or {}
    msg: str = error.get("msg", "Invalid value")

    if etype == "missing" or (etype == "string_too_short" and error.get("input") == ""):
        return f"{label} is required"
    if etype == "string_too_short":
        return f"{label} must be at least {ctx.get('min_length')} characters"
    if etype == "string_too_long":
        return f"{label} must be at most {ctx.get('max_length')} characters"
    if etype == "string_pattern_mismatch":
        return PATTERN_MESSAGES.get(leaf, f"{label} has an invalid format")
    if etype == "greater_than":
        return f"{label} must be greater than {_num(ctx.get('gt'))}"
    if etype == "greater_than_equal":
        return f"{label} must be at least {_num(ctx.get('ge'))}"
    if etype in ("less_than_equal", "less_than"):
        return f"{label} must be at most {_num(ctx.get('le', ctx.get('lt')))}"
    if etype in ("int_parsing", "int_from_float", "int_type"):
        return f"{label} must be a whole number"
    if etype in ("float_parsing", "float_type", "finite_number"):
        return f"{label} must be a number"
    if etype in ("bool_parsing", "bool_type"):
        return f"{label} must be true or false"
    if etype == "literal_error":
        return f"{label} must be one of: {ctx.get('expected', '')}"
    if etype == "extra_forbidden":
        return f"Unknown field '{leaf}'"
    if etype == "value_error":
        return msg.removeprefix("Value error, ")
    if etype in ("string_type", "model_attributes_type", "dict_type", "json_invalid"):
        return f"{label} has an invalid type" if field != "body" else "Request body is invalid"
    return msg


def error_list(errors: Iterable[Mapping[str, Any]]) -> list[dict[str, str]]:
    result = []
    for e in errors:
        if e.get("type") == "json_invalid":
            # loc is ("body", <char offset>) - an offset is not a field name.
            result.append({"field": "body", "message": "Request body is not valid JSON"})
        else:
            result.append({"field": _field_name(e.get("loc", ())), "message": friendly_message(e)})
    return result


def parse_form[M: BaseModel](
    model: type[M], form: Mapping[str, Any], fields: Iterable[str]
) -> tuple[M | None, dict[str, str]]:
    """Validate selected form fields with ``model``.

    Empty inputs are treated as "not provided" so required fields report
    "X is required" and optional ones fall back to their defaults.
    Returns (model_or_None, {field: first_error_message}).
    """
    data = {f: form[f] for f in fields if f in form and str(form[f]).strip() != ""}
    try:
        return model.model_validate(data), {}
    except ValidationError as exc:
        messages: dict[str, str] = {}
        for item in error_list(exc.errors()):
            messages.setdefault(item["field"], item["message"])
        return None, messages
