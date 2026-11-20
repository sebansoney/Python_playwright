"""Request/response models and validation rules.

The SAME models validate API JSON bodies and HTML form posts, so a rule (e.g. the
password policy) behaves identically in the UI and the API - which is exactly what
cross-layer integration tests rely on.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, computed_field

CATEGORIES: tuple[str, ...] = ("Books", "Clothing", "Electronics", "Home", "Sports", "Toys")
Category = Literal["Books", "Clothing", "Electronics", "Home", "Sports", "Toys"]
Role = Literal["admin", "user"]
ProductSort = Literal["name_asc", "name_desc", "price_asc", "price_desc", "newest"]

_EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}$")
PHONE_PATTERN = r"^\+?[0-9][0-9 \-]{6,19}$"
SKU_PATTERN = r"^[A-Z0-9][A-Z0-9-]{2,19}$"


def _email(value: str) -> str:
    value = value.strip().lower()
    if not _EMAIL_RE.match(value):
        raise ValueError("Enter a valid email address")
    return value


def _password(value: str) -> str:
    if len(value.encode("utf-8")) > 72:
        raise ValueError("Password is too long")
    if not re.search(r"[A-Za-z]", value) or not re.search(r"\d", value):
        raise ValueError("Password must contain at least one letter and one number")
    return value


def _upper(value: str) -> str:
    return value.upper()


def _two_decimals(value: float) -> float:
    if round(value, 2) != value:
        raise ValueError("Price can have at most 2 decimal places")
    return value


Email = Annotated[str, Field(max_length=120), AfterValidator(_email)]
Password = Annotated[str, Field(min_length=8, max_length=64), AfterValidator(_password)]
FullName = Annotated[str, Field(min_length=2, max_length=60)]
Phone = Annotated[str, Field(pattern=PHONE_PATTERN)]
ProductName = Annotated[str, Field(min_length=2, max_length=80)]
Sku = Annotated[str, AfterValidator(_upper), Field(pattern=SKU_PATTERN)]
Price = Annotated[float, Field(gt=0, le=100_000), AfterValidator(_two_decimals)]
Stock = Annotated[int, Field(ge=0, le=100_000)]
Description = Annotated[str, Field(max_length=500)]

# Friendly messages for regex failures (used by both API and web error formatting).
PATTERN_MESSAGES = {
    "phone": "Enter a valid phone number (digits, spaces, dashes, optional leading +)",
    "sku": "SKU must be 3-20 characters: letters, digits or dashes",
}


class _In(BaseModel):
    """Input models: trim strings and reject unknown fields (catches payload typos)."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")


# --------------------------------------------------------------------- auth
class LoginRequest(_In):
    email: Annotated[str, Field(min_length=1)]
    password: Annotated[str, Field(min_length=1)]


class RegisterRequest(_In):
    email: Email
    full_name: FullName
    password: Password


# -------------------------------------------------------------------- users
class UserCreate(_In):
    email: Email
    full_name: FullName
    password: Password
    role: Role = "user"
    phone: Phone | None = None


class UserUpdate(_In):
    """PUT - full replacement of editable fields (password excluded)."""

    email: Email
    full_name: FullName
    role: Role
    is_active: bool
    phone: Phone | None = None


class UserPatch(_In):
    email: Email | None = None
    full_name: FullName | None = None
    role: Role | None = None
    is_active: bool | None = None
    phone: Phone | None = None


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    full_name: str
    phone: str | None
    role: Role
    is_active: bool
    has_avatar: bool
    created_at: datetime
    updated_at: datetime


class TokenResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int
    user: UserOut


# ------------------------------------------------------------------ profile
class ProfileUpdate(_In):
    full_name: FullName
    phone: Phone | None = None


class PasswordChange(_In):
    current_password: Annotated[str, Field(min_length=1)]
    new_password: Password


# ----------------------------------------------------------------- products
class ProductCreate(_In):
    name: ProductName
    sku: Sku
    category: Category
    price: Price
    stock: Stock = 0
    description: Description | None = None


class ProductUpdate(_In):
    """PUT - every field required."""

    name: ProductName
    sku: Sku
    category: Category
    price: Price
    stock: Stock
    description: Description | None = None


class ProductPatch(_In):
    name: ProductName | None = None
    sku: Sku | None = None
    category: Category | None = None
    price: Price | None = None
    stock: Stock | None = None
    description: Description | None = None


class ProductOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

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

    @computed_field  # type: ignore[prop-decorator]
    @property
    def in_stock(self) -> bool:
        return self.stock > 0


class ProductFilters(BaseModel):
    q: str | None = None
    category: Category | None = None
    min_price: float | None = Field(None, ge=0)
    max_price: float | None = Field(None, ge=0)
    in_stock: bool = False
    sort: ProductSort = "name_asc"
    page: int = Field(1, ge=1)
    size: int = Field(10, ge=1, le=100)


# ------------------------------------------------------------------- common
class Page[T](BaseModel):
    items: list[T]
    total: int
    page: int
    size: int

    @computed_field  # type: ignore[prop-decorator]
    @property
    def pages(self) -> int:
        return max(1, -(-self.total // self.size))


class FieldError(BaseModel):
    field: str
    message: str


class ErrorResponse(BaseModel):
    detail: str
    code: str
    correlation_id: str | None = None
    errors: list[FieldError] | None = None


class Notification(BaseModel):
    id: str
    level: Literal["info", "warning", "success"]
    message: str
