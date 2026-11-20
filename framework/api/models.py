"""Typed response models (pydantic) for convenient, typed access in tests.

Two complementary checks exist on purpose:
  * JSON Schema files (framework/api/schemas) = the *contract*: language-neutral,
    shareable with developers, strict about extra/missing fields.
  * These pydantic models = *typed parsing* so tests read ``user.email`` instead of
    ``body["email"]``. ``extra="forbid"`` also flags unexpected fields.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class User(_Strict):
    id: int
    email: str
    full_name: str
    phone: str | None
    role: Literal["admin", "user"]
    is_active: bool
    has_avatar: bool
    created_at: datetime
    updated_at: datetime


class Product(_Strict):
    id: int
    name: str
    sku: str
    category: str
    price: float
    stock: int
    description: str | None
    created_by_id: int | None
    created_at: datetime
    updated_at: datetime
    in_stock: bool


class Page[T](_Strict):
    items: list[T]
    total: int
    page: int
    size: int
    pages: int


class Token(_Strict):
    access_token: str
    token_type: Literal["bearer"]
    expires_in: int
    user: User


class FieldError(_Strict):
    field: str
    message: str


class Error(_Strict):
    detail: str
    code: str
    correlation_id: str | None
    errors: list[FieldError] | None = None

    def message_for(self, field: str) -> str | None:
        return next((e.message for e in self.errors or [] if e.field == field), None)
