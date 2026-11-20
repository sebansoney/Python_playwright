"""Data access + business rules shared by the API and the web pages.

Keeping this in one place means the UI and the API cannot drift apart:
duplicate checks, self-delete protection, filtering, etc. are implemented once.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from sqlalchemy import Select, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from sample_application.backend.errors import AppError, not_found
from sample_application.backend.models import Product, User
from sample_application.backend.schemas import (
    CATEGORIES,
    ProductCreate,
    ProductFilters,
    UserCreate,
)
from sample_application.backend.security import hash_password, verify_password

LOW_STOCK_THRESHOLD = 5
AVATAR_TYPES = {"image/png", "image/jpeg"}
AVATAR_MAX_BYTES = 1_000_000


# ======================================================================= users
def get_user(db: Session, user_id: int) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise not_found("User")
    return user


def get_user_by_email(db: Session, email: str) -> User | None:
    return db.scalar(select(User).where(User.email == email.strip().lower()))


def authenticate(db: Session, email: str, password: str) -> User:
    user = get_user_by_email(db, email)
    if user is None or not verify_password(password, user.password_hash):
        raise AppError(401, "Invalid email or password", code="invalid_credentials")
    if not user.is_active:
        raise AppError(403, "Account is disabled", code="account_disabled")
    return user


def _ensure_email_free(db: Session, email: str, exclude_id: int | None = None) -> None:
    existing = get_user_by_email(db, email)
    if existing is not None and existing.id != exclude_id:
        raise AppError(409, "A user with this email already exists", code="duplicate_email")


def list_users(
    db: Session, q: str | None = None, role: str | None = None, page: int = 1, size: int = 20
) -> tuple[list[User], int]:
    stmt = select(User)
    if q:
        like = f"%{q.strip().lower()}%"
        stmt = stmt.where(or_(func.lower(User.full_name).like(like), User.email.like(like)))
    if role:
        stmt = stmt.where(User.role == role)
    return _paged(db, stmt, (User.id,), page, size)


def create_user(db: Session, data: UserCreate) -> User:
    _ensure_email_free(db, data.email)
    user = User(
        email=data.email,
        full_name=data.full_name,
        phone=data.phone,
        role=data.role,
        password_hash=hash_password(data.password),
    )
    db.add(user)
    _commit(db, "A user with this email already exists", "duplicate_email")
    db.refresh(user)
    return user


def update_user(db: Session, user: User, changes: dict[str, Any], acting: User) -> User:
    if "email" in changes:
        _ensure_email_free(db, changes["email"], exclude_id=user.id)
    is_self_admin = user.id == acting.id and acting.role == "admin"
    if is_self_admin and (
        changes.get("role", "admin") != "admin" or changes.get("is_active", True) is False
    ):
        raise AppError(400, "You cannot demote or deactivate your own account", "self_lockout")
    for key, value in changes.items():
        setattr(user, key, value)
    _commit(db, "A user with this email already exists", "duplicate_email")
    db.refresh(user)
    return user


def delete_user(db: Session, user: User, acting: User) -> None:
    if user.id == acting.id:
        raise AppError(400, "You cannot delete your own account", code="self_delete")
    db.delete(user)
    db.commit()


def change_password(db: Session, user: User, current: str, new: str) -> None:
    if not verify_password(current, user.password_hash):
        raise AppError(400, "Current password is incorrect", code="wrong_password")
    user.password_hash = hash_password(new)
    db.commit()


def set_avatar(db: Session, user: User, content: bytes, content_type: str | None) -> None:
    if content_type not in AVATAR_TYPES:
        raise AppError(415, "Avatar must be a PNG or JPEG image")
    if not content:
        raise AppError(400, "The uploaded file is empty", code="empty_file")
    if len(content) > AVATAR_MAX_BYTES:
        raise AppError(413, "Avatar must be 1 MB or smaller")
    user.avatar = content
    user.avatar_content_type = content_type
    db.commit()


# ==================================================================== products
def get_product(db: Session, product_id: int) -> Product:
    product = db.get(Product, product_id)
    if product is None:
        raise not_found("Product")
    return product


def _ensure_sku_free(db: Session, sku: str, exclude_id: int | None = None) -> None:
    existing = db.scalar(select(Product).where(Product.sku == sku))
    if existing is not None and existing.id != exclude_id:
        raise AppError(409, "A product with this SKU already exists", code="duplicate_sku")


_SORTS = {
    "name_asc": (Product.name.asc(),),
    "name_desc": (Product.name.desc(),),
    "price_asc": (Product.price.asc(), Product.name.asc()),
    "price_desc": (Product.price.desc(), Product.name.asc()),
    "newest": (Product.created_at.desc(), Product.id.desc()),
}


def list_products(db: Session, f: ProductFilters) -> tuple[list[Product], int]:
    stmt = select(Product)
    if f.q:
        like = f"%{f.q.strip().lower()}%"
        stmt = stmt.where(
            or_(
                func.lower(Product.name).like(like),
                func.lower(Product.sku).like(like),
                func.lower(Product.description).like(like),
            )
        )
    if f.category:
        stmt = stmt.where(Product.category == f.category)
    if f.min_price is not None:
        stmt = stmt.where(Product.price >= f.min_price)
    if f.max_price is not None:
        stmt = stmt.where(Product.price <= f.max_price)
    if f.in_stock:
        stmt = stmt.where(Product.stock > 0)
    return _paged(db, stmt, _SORTS[f.sort], f.page, f.size)


def create_product(db: Session, data: ProductCreate, creator: User | None) -> Product:
    _ensure_sku_free(db, data.sku)
    product = Product(**data.model_dump(), created_by_id=creator.id if creator else None)
    db.add(product)
    _commit(db, "A product with this SKU already exists", "duplicate_sku")
    db.refresh(product)
    return product


def update_product(db: Session, product: Product, changes: dict[str, Any]) -> Product:
    if "sku" in changes:
        _ensure_sku_free(db, changes["sku"], exclude_id=product.id)
    for key, value in changes.items():
        setattr(product, key, value)
    _commit(db, "A product with this SKU already exists", "duplicate_sku")
    db.refresh(product)
    return product


def delete_product(db: Session, product: Product) -> None:
    db.delete(product)
    db.commit()


def all_products(db: Session) -> list[Product]:
    return list(db.scalars(select(Product).order_by(Product.id)).all())


# ===================================================================== stats
def dashboard_stats(db: Session) -> dict[str, Any]:
    return {
        "users": db.scalar(select(func.count(User.id))) or 0,
        "products": db.scalar(select(func.count(Product.id))) or 0,
        "low_stock": db.scalar(
            select(func.count(Product.id)).where(Product.stock < LOW_STOCK_THRESHOLD)
        )
        or 0,
        "categories": len(CATEGORIES),
        "recent_products": list(
            db.scalars(
                select(Product).order_by(Product.created_at.desc(), Product.id.desc()).limit(5)
            )
        ),
    }


# ==================================================================== helpers
def _paged[T](
    db: Session, stmt: Select[tuple[T]], order_by: Sequence[Any], page: int, size: int
) -> tuple[list[T], int]:
    """Return (items, total) from ONE statement so both come from the same snapshot.

    Two separate queries (COUNT, then SELECT ... LIMIT) can see different data when
    another request commits in between - a page then held 16 items while claiming
    total=15 (found by a parallel test run). ``COUNT(*) OVER ()`` attaches the total
    to every row of the page in a single query.
    """
    windowed = (
        stmt.add_columns(func.count().over().label("_total"))
        .order_by(*order_by)
        .offset((page - 1) * size)
        .limit(size)
    )
    rows = db.execute(windowed).all()
    if rows:
        return [row[0] for row in rows], int(rows[0][-1])
    # Empty page (no matches, or page beyond the end): a plain count is consistent here.
    return [], db.scalar(select(func.count()).select_from(stmt.subquery())) or 0


def _commit(db: Session, conflict_message: str, conflict_code: str) -> None:
    """Commit; a UNIQUE race between parallel requests becomes a clean 409."""
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise AppError(409, conflict_message, code=conflict_code) from exc
