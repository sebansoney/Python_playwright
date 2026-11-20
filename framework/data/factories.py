"""Test data builders (Faker).

Every value that must be unique (email, SKU, names used in searches) carries a
short random token, so tests never collide - even in parallel or on re-runs.
Override any field: ``build_product(price=0)`` for a negative case.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import asdict, dataclass, field

from faker import Faker

fake = Faker()

CATEGORIES = ("Books", "Clothing", "Electronics", "Home", "Sports", "Toys")
TEST_EMAIL_DOMAIN = "example.test"  # reserved TLD: can never reach a real mailbox


def token(length: int = 8) -> str:
    return uuid.uuid4().hex[:length]


@dataclass
class UserData:
    full_name: str
    email: str
    password: str
    role: str = "user"
    phone: str | None = None

    def to_api(self) -> dict[str, object]:
        return {k: v for k, v in asdict(self).items() if v is not None}


@dataclass
class ProductData:
    name: str
    sku: str
    category: str
    price: float
    stock: int = 10
    description: str | None = field(default=None)

    def to_api(self) -> dict[str, object]:
        return {k: v for k, v in asdict(self).items() if v is not None}

    @property
    def price_text(self) -> str:
        return f"{self.price:.2f}"


def build_user(**overrides: object) -> UserData:
    t = token()
    first, last = fake.first_name(), fake.last_name()
    data = UserData(
        full_name=f"{first} {last}"[:50] + f" {t[:4]}",
        email=re.sub(r"[^a-z0-9.]", "", f"{first}.{last}.{t}".lower()) + f"@{TEST_EMAIL_DOMAIN}",
        # Policy: 8-64 chars, at least one letter and one digit.
        password=f"Pw{t}{fake.random_int(10, 99)}!",
    )
    for key, value in overrides.items():
        setattr(data, key, value)
    return data


def build_product(**overrides: object) -> ProductData:
    t = token().upper()
    data = ProductData(
        name=f"{fake.color_name()} {fake.word().capitalize()} {t}",
        sku=f"AT-{t}",
        category=fake.random_element(CATEGORIES),
        price=round(fake.pyfloat(min_value=1, max_value=500, right_digits=2), 2),
        stock=fake.random_int(1, 100),
        description=fake.sentence(nb_words=8),
    )
    for key, value in overrides.items():
        setattr(data, key, value)
    return data
