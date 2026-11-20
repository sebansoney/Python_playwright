"""Product pages: list with search/filters/sort/paging, detail, add, edit, delete."""

from typing import Any
from urllib.parse import urlencode

from fastapi import APIRouter, Request
from fastapi.responses import Response
from pydantic import ValidationError

from sample_application.backend import repository as repo
from sample_application.backend.deps import DbSession
from sample_application.backend.errors import AppError
from sample_application.backend.schemas import ProductCreate, ProductFilters, ProductUpdate
from sample_application.backend.validation import error_list, parse_form
from sample_application.backend.web.common import WebUser, redirect, render

router = APIRouter(prefix="/products")

_FIELDS = ("name", "sku", "category", "price", "stock", "description")
_FILTER_KEYS = ("q", "category", "min_price", "max_price", "in_stock", "sort")


@router.get("")
def products_list(request: Request, db: DbSession, _user: WebUser) -> Response:
    raw: dict[str, Any] = {
        k: v for k, v in request.query_params.items() if k in (*_FILTER_KEYS, "page") and v != ""
    }
    raw["in_stock"] = raw.get("in_stock") in ("on", "true", "1")
    filter_errors: list[str] = []
    try:
        filters = ProductFilters(**raw, size=10)
    except ValidationError as exc:
        filter_errors = [e["message"] for e in error_list(exc.errors())]
        filters = ProductFilters(size=10)
    if (
        filters.min_price is not None
        and filters.max_price is not None
        and filters.min_price > filters.max_price
    ):
        filter_errors.append("Minimum price cannot be greater than maximum price")
    products, total = ([], 0) if filter_errors else repo.list_products(db, filters)
    pages = max(1, -(-total // filters.size))
    # Querystring without "page" - reused by the pagination links.
    base_query = urlencode(
        [(k, v) for k, v in request.query_params.items() if k in _FILTER_KEYS and v != ""]
    )
    return render(
        request,
        "products.html",
        {
            "products": products,
            "total": total,
            "filters": filters,
            "raw": request.query_params,
            "filter_errors": filter_errors,
            "page": filters.page,
            "pages": pages,
            "base_query": base_query,
        },
    )


@router.get("/new")
def product_new(request: Request, _user: WebUser) -> Response:
    return render(
        request, "product_form.html", {"form": {"stock": "0"}, "errors": {}, "product": None}
    )


@router.post("/new")
async def product_create(request: Request, db: DbSession, user: WebUser) -> Response:
    form = await request.form()
    data, errors = parse_form(ProductCreate, form, _FIELDS)
    if data:
        try:
            repo.create_product(db, data, creator=user)
        except AppError as exc:
            errors["sku"] = str(exc.detail)
        else:
            return redirect("/products", flash="product_created")
    values = {k: str(form.get(k, "")) for k in _FIELDS}
    return render(
        request, "product_form.html", {"form": values, "errors": errors, "product": None}, 400
    )


@router.get("/{product_id}")
def product_detail(product_id: int, request: Request, db: DbSession, _user: WebUser) -> Response:
    return render(request, "product_detail.html", {"product": repo.get_product(db, product_id)})


@router.get("/{product_id}/edit")
def product_edit(product_id: int, request: Request, db: DbSession, _user: WebUser) -> Response:
    p = repo.get_product(db, product_id)
    form = {k: "" if getattr(p, k) is None else str(getattr(p, k)) for k in _FIELDS}
    form["price"] = f"{p.price:.2f}"
    return render(request, "product_form.html", {"form": form, "errors": {}, "product": p})


@router.post("/{product_id}/edit")
async def product_update(
    product_id: int, request: Request, db: DbSession, _user: WebUser
) -> Response:
    product = repo.get_product(db, product_id)
    form = await request.form()
    data, errors = parse_form(ProductUpdate, form, _FIELDS)
    if data:
        try:
            repo.update_product(db, product, data.model_dump())
        except AppError as exc:
            errors["sku"] = str(exc.detail)
        else:
            return redirect("/products", flash="product_updated")
    values = {k: str(form.get(k, "")) for k in _FIELDS}
    return render(
        request, "product_form.html", {"form": values, "errors": errors, "product": product}, 400
    )


@router.post("/{product_id}/delete")
def product_delete(product_id: int, db: DbSession, _user: WebUser) -> Response:
    repo.delete_product(db, repo.get_product(db, product_id))
    return redirect("/products", flash="product_deleted")
