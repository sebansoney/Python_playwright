from typing import Annotated

from fastapi import APIRouter, Query, Response, status

from sample_application.backend import repository as repo
from sample_application.backend.deps import CurrentUser, DbSession
from sample_application.backend.errors import AppError
from sample_application.backend.schemas import (
    CATEGORIES,
    Page,
    ProductCreate,
    ProductFilters,
    ProductOut,
    ProductPatch,
    ProductUpdate,
)

router = APIRouter(prefix="/products", tags=["products"])


@router.get("")
def list_products(
    db: DbSession, _user: CurrentUser, filters: Annotated[ProductFilters, Query()]
) -> Page[ProductOut]:
    rows, total = repo.list_products(db, filters)
    return Page[ProductOut](
        items=[ProductOut.model_validate(p) for p in rows],
        total=total,
        page=filters.page,
        size=filters.size,
    )


@router.get("/categories")
def list_categories(_user: CurrentUser) -> list[str]:
    return list(CATEGORIES)


@router.post("", status_code=status.HTTP_201_CREATED)
def create_product(
    body: ProductCreate, db: DbSession, user: CurrentUser, response: Response
) -> ProductOut:
    product = repo.create_product(db, body, creator=user)
    response.headers["Location"] = f"/api/v1/products/{product.id}"
    return ProductOut.model_validate(product)


@router.get("/{product_id}")
def get_product(product_id: int, db: DbSession, _user: CurrentUser) -> ProductOut:
    return ProductOut.model_validate(repo.get_product(db, product_id))


@router.put("/{product_id}")
def replace_product(
    product_id: int, body: ProductUpdate, db: DbSession, _user: CurrentUser
) -> ProductOut:
    product = repo.get_product(db, product_id)
    return ProductOut.model_validate(repo.update_product(db, product, body.model_dump()))


@router.patch("/{product_id}")
def patch_product(
    product_id: int, body: ProductPatch, db: DbSession, _user: CurrentUser
) -> ProductOut:
    changes = body.model_dump(exclude_unset=True)
    if not changes:
        raise AppError(400, "No fields to update", code="empty_patch")
    product = repo.get_product(db, product_id)
    return ProductOut.model_validate(repo.update_product(db, product, changes))


@router.delete("/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_product(product_id: int, db: DbSession, _user: CurrentUser) -> None:
    repo.delete_product(db, repo.get_product(db, product_id))
