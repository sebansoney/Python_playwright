"""ORM models."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import ForeignKey, LargeBinary, Numeric, String
from sqlalchemy.orm import Mapped, deferred, mapped_column

from sample_application.backend.database import Base


def utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class User(Base):
    __tablename__ = "users"
    # AUTOINCREMENT: never reuse ids of deleted rows (SQLite's default does), so a
    # stale id can never silently point at a different, newer record.
    __table_args__ = {"sqlite_autoincrement": True}  # noqa: RUF012 - SQLAlchemy convention

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(60))
    phone: Mapped[str | None] = mapped_column(String(20), default=None)
    role: Mapped[str] = mapped_column(String(10), default="user")
    is_active: Mapped[bool] = mapped_column(default=True)
    password_hash: Mapped[str] = mapped_column(String(100))
    avatar: Mapped[bytes | None] = deferred(mapped_column(LargeBinary, default=None))
    avatar_content_type: Mapped[str | None] = mapped_column(String(30), default=None)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)

    @property
    def has_avatar(self) -> bool:
        return self.avatar_content_type is not None


class Product(Base):
    __tablename__ = "products"
    __table_args__ = {"sqlite_autoincrement": True}  # noqa: RUF012 - see User

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80), index=True)
    sku: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    category: Mapped[str] = mapped_column(String(30), index=True)
    price: Mapped[float] = mapped_column(Numeric(10, 2, asdecimal=False))
    stock: Mapped[int] = mapped_column(default=0)
    description: Mapped[str | None] = mapped_column(String(500), default=None)
    created_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), default=None
    )
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)

    @property
    def in_stock(self) -> bool:
        return self.stock > 0
