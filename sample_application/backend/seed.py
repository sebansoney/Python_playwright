"""Database creation and deterministic seed data.

Seed data is *reference* data: tests may read it but must create their own
records for anything they modify, so tests stay independent and parallel-safe.
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from sample_application.backend.config import config
from sample_application.backend.database import Base, SessionLocal, engine
from sample_application.backend.models import Product, User
from sample_application.backend.security import hash_password

# (name, sku, category, price, stock, description)
SEED_PRODUCTS: list[tuple[str, str, str, float, int, str]] = [
    ("Wireless Mouse", "EL-1001", "Electronics", 24.99, 120, "Ergonomic 2.4 GHz mouse"),
    ("Mechanical Keyboard", "EL-1002", "Electronics", 89.50, 35, "Hot-swappable switches"),
    ("USB-C Hub", "EL-1003", "Electronics", 39.00, 0, "7-in-1 hub with HDMI"),
    ("Noise Cancelling Headphones", "EL-1004", "Electronics", 199.99, 12, "Over-ear, 30h battery"),
    ("Python Testing Handbook", "BK-2001", "Books", 34.90, 50, "Practical pytest patterns"),
    ("Clean Architecture Notes", "BK-2002", "Books", 27.00, 3, "Software design essentials"),
    ("The Automation Mindset", "BK-2003", "Books", 19.95, 0, "Thinking like a test architect"),
    ("Cotton T-Shirt", "CL-3001", "Clothing", 15.00, 200, "100% organic cotton"),
    ("Rain Jacket", "CL-3002", "Clothing", 79.00, 8, "Waterproof and breathable"),
    ("Ceramic Coffee Mug", "HM-4001", "Home", 9.99, 75, "350 ml, dishwasher safe"),
    ("Desk Lamp", "HM-4002", "Home", 45.00, 4, "LED with dimmer"),
    ("Yoga Mat", "SP-5001", "Sports", 29.99, 40, "Non-slip, 6 mm"),
    ("Running Shoes", "SP-5002", "Sports", 120.00, 15, "Lightweight trainers"),
    ("Building Blocks Set", "TY-6001", "Toys", 49.99, 22, "500 pieces"),
    ("Puzzle 1000 Pieces", "TY-6002", "Toys", 14.50, 2, "Landscape puzzle"),
]

# (full_name, email, role, is_active)
SEED_EXTRA_USERS: list[tuple[str, str, str, bool]] = [
    ("Grace Hopper", "grace.hopper@example.test", "user", True),
    ("Alan Turing", "alan.turing@example.test", "user", True),
    ("Disabled Account", "disabled.user@example.test", "user", False),
]


def seed(db: Session) -> None:
    admin = User(
        email=config.admin_email,
        full_name="Admin User",
        role="admin",
        password_hash=hash_password(config.admin_password),
    )
    user = User(
        email=config.user_email,
        full_name="Standard User",
        role="user",
        password_hash=hash_password(config.user_password),
    )
    db.add_all([admin, user])
    # Extra users get the standard user's password; they exist for list/search tests.
    shared_hash = user.password_hash
    db.add_all(
        User(email=e, full_name=n, role=r, is_active=a, password_hash=shared_hash)
        for n, e, r, a in SEED_EXTRA_USERS
    )
    db.flush()
    db.add_all(
        Product(name=n, sku=s, category=c, price=p, stock=q, description=d, created_by_id=admin.id)
        for n, s, c, p, q, d in SEED_PRODUCTS
    )
    db.commit()


def init_db(reset: bool = False) -> None:
    """Create tables; seed when empty. ``reset=True`` wipes everything first."""
    if reset:
        Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        if (db.scalar(select(func.count(User.id))) or 0) == 0:
            seed(db)
