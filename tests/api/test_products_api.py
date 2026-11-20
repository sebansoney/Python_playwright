"""Products resource: query features, CRUD chain, validation and boundaries."""

from collections.abc import Callable
from typing import Any

import pytest

from framework.api.clients import ApiSession
from framework.api.models import Page, Product
from framework.assertions import expect_api
from framework.data.backdoor import Backdoor
from framework.data.cleanup import CleanupRegistry
from framework.data.factories import ProductData, build_product

ProductFactory = Callable[..., tuple[ProductData, dict[str, Any]]]


@pytest.fixture
def new_product_payload(backdoor: Backdoor, cleanup: CleanupRegistry) -> dict[str, Any]:
    product = build_product()
    cleanup.add(f"delete product {product.sku}", backdoor.delete_product_by_sku, product.sku)
    return product.to_api()


def _products(response: Any) -> Page[Product]:
    return expect_api(response).has_status(200).matches_schema("product_page").parse(Page[Product])


# ----------------------------------------------------------------- query
@pytest.mark.smoke
def test_list_products_matches_contract(user_api: ApiSession) -> None:
    page = _products(user_api.products.list())

    assert page.total >= 15  # seeded reference data
    assert page.size == 10  # default page size
    assert len(page.items) == 10


@pytest.mark.regression
def test_filter_by_category_and_stock(user_api: ApiSession) -> None:
    page = _products(user_api.products.list(category="Books", in_stock=True, size=100))

    skus = {p.sku for p in page.items}
    assert {"BK-2001", "BK-2002"} <= skus
    assert "BK-2003" not in skus  # seeded Book with stock 0
    assert all(p.category == "Books" and p.in_stock for p in page.items)


@pytest.mark.regression
def test_price_range_with_descending_sort(user_api: ApiSession) -> None:
    page = _products(
        user_api.products.list(min_price=20, max_price=100, sort="price_desc", size=100)
    )

    prices = [p.price for p in page.items]
    assert prices
    assert all(20 <= p <= 100 for p in prices)
    assert prices == sorted(prices, reverse=True)


@pytest.mark.regression
def test_search_matches_name_sku_and_description(user_api: ApiSession) -> None:
    assert [p.sku for p in _products(user_api.products.list(q="wireless mouse")).items] == [
        "EL-1001"
    ]
    assert [p.sku for p in _products(user_api.products.list(q="el-1002")).items] == ["EL-1002"]
    assert [p.sku for p in _products(user_api.products.list(q="dishwasher")).items] == ["HM-4001"]


@pytest.mark.regression
@pytest.mark.parametrize(
    ("params", "status", "field", "message"),
    [
        ({"size": 1}, 200, None, None),
        ({"size": 100}, 200, None, None),
        ({"size": 0}, 422, "size", "Page size must be at least 1"),
        ({"size": 101}, 422, "size", "Page size must be at most 100"),
        ({"page": 0}, 422, "page", "Page must be at least 1"),
        ({"min_price": -1}, 422, "min_price", "Minimum price must be at least 0"),
        ({"category": "Cars"}, 422, "category", None),
        ({"sort": "random"}, 422, "sort", None),
    ],
    ids=[
        "size-1",
        "size-100",
        "size-0",
        "size-101",
        "page-0",
        "negative-min-price",
        "unknown-category",
        "unknown-sort",
    ],
)
def test_query_parameter_boundaries(
    user_api: ApiSession,
    params: dict[str, Any],
    status: int,
    field: str | None,
    message: str | None,
) -> None:
    response = user_api.products.list(**params)

    if status == 200:
        page = _products(response)
        assert len(page.items) == min(params["size"], page.total)
    else:
        expect_api(response).is_error(422, "validation_error").has_field_error(field, message)  # type: ignore[arg-type]


# ----------------------------------------------------------- CRUD chain
@pytest.mark.smoke
def test_product_crud_lifecycle(user_api: ApiSession, new_product_payload: dict[str, Any]) -> None:
    """API chaining: create -> read -> find -> patch -> put -> delete -> 404."""
    products = user_api.products

    created = (
        expect_api(products.create(new_product_payload))
        .has_status(201)
        .matches_schema("product")
        .parse(Product)
    )
    pid = created.id

    expect_api(products.get(pid)).has_status(200).json_contains(new_product_payload)
    found = _products(products.list(q=created.sku))
    assert [p.id for p in found.items] == [pid]

    expect_api(products.update(pid, {"stock": 0})).has_status(200).json_contains(
        {"stock": 0, "in_stock": False, "name": created.name}
    )
    replacement = {**new_product_payload, "name": "Replaced Name", "price": 1.5, "stock": 3}
    expect_api(products.replace(pid, replacement)).has_status(200).json_contains(
        {"name": "Replaced Name", "price": 1.5, "stock": 3, "in_stock": True}
    )

    expect_api(products.delete(pid)).has_status(204)
    expect_api(products.get(pid)).is_error(404, "not_found").has_detail("Product not found")


@pytest.mark.regression
def test_sku_is_normalised_and_unique(
    user_api: ApiSession, new_product_payload: dict[str, Any]
) -> None:
    payload = {**new_product_payload, "sku": new_product_payload["sku"].lower()}

    first = user_api.products.create(payload)
    second = user_api.products.create({**payload, "name": "Another name"})

    expect_api(first).has_status(201).has_json("sku", new_product_payload["sku"])
    expect_api(second).is_error(409, "duplicate_sku").has_detail(
        "A product with this SKU already exists"
    )


# ---------------------------------------------------- validation / limits
@pytest.mark.regression
@pytest.mark.parametrize(
    ("price", "status", "message"),
    [
        (0, 422, "Price must be greater than 0"),
        (0.01, 201, None),
        (100_000, 201, None),
        (100_000.01, 422, "Price must be at most 100000"),
        (1.999, 422, "Price can have at most 2 decimal places"),
        (-5, 422, "Price must be greater than 0"),
    ],
    ids=["zero", "min", "max", "above-max", "three-decimals", "negative"],
)
def test_price_boundaries(
    user_api: ApiSession,
    new_product_payload: dict[str, Any],
    price: float,
    status: int,
    message: str | None,
) -> None:
    response = user_api.products.create({**new_product_payload, "price": price})

    if status == 201:
        expect_api(response).has_status(201).has_json("price", price)
    else:
        expect_api(response).is_error(422).has_field_error("price", message)


@pytest.mark.regression
@pytest.mark.parametrize(
    ("stock", "status", "message"),
    [
        (-1, 422, "Stock must be at least 0"),
        (0, 201, None),
        (100_000, 201, None),
        (100_001, 422, "Stock must be at most 100000"),
    ],
    ids=["negative", "zero", "max", "above-max"],
)
def test_stock_boundaries(
    user_api: ApiSession,
    new_product_payload: dict[str, Any],
    stock: int,
    status: int,
    message: str | None,
) -> None:
    response = user_api.products.create({**new_product_payload, "stock": stock})

    if status == 201:
        expect_api(response).has_status(201).json_contains({"stock": stock, "in_stock": stock > 0})
    else:
        expect_api(response).is_error(422).has_field_error("stock", message)


@pytest.mark.regression
def test_create_product_missing_mandatory_fields(user_api: ApiSession) -> None:
    response = user_api.products.create({})

    expect_api(response).is_error(422, "validation_error").has_field_errors_exactly(
        "name", "sku", "category", "price"
    ).has_field_error("price", "Price is required")


@pytest.mark.regression
@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("price", "abc", "Price must be a number"),
        ("stock", 1.5, "Stock must be a whole number"),
        ("name", "X", "Name must be at least 2 characters"),
        ("sku", "has space", "SKU must be 3-20 characters: letters, digits or dashes"),
        ("description", "d" * 501, "Description must be at most 500 characters"),
    ],
    ids=["price-text", "stock-fraction", "name-too-short", "sku-pattern", "description-too-long"],
)
def test_create_product_invalid_payload(
    user_api: ApiSession, new_product_payload: dict[str, Any], field: str, value: Any, message: str
) -> None:
    response = user_api.products.create({**new_product_payload, field: value})

    expect_api(response).is_error(422, "validation_error").has_field_error(field, message)


@pytest.mark.regression
def test_malformed_json_body_is_rejected(user_api: ApiSession) -> None:
    response = user_api.client.post(
        user_api.products.base,
        content=b'{"name": "broken',
        headers={"Content-Type": "application/json"},
    )

    expect_api(response).is_error(422, "validation_error").has_field_error(
        "body", "Request body is not valid JSON"
    )


@pytest.mark.regression
@pytest.mark.parametrize("method", ["get", "update", "replace", "delete"])
def test_unknown_product_returns_404(
    user_api: ApiSession, new_product_payload: dict[str, Any], method: str
) -> None:
    products = user_api.products
    call = {
        "get": lambda: products.get(999_999_999),
        "update": lambda: products.update(999_999_999, {"stock": 1}),
        "replace": lambda: products.replace(999_999_999, new_product_payload),
        "delete": lambda: products.delete(999_999_999),
    }[method]

    expect_api(call()).is_error(404, "not_found").has_detail("Product not found")


@pytest.mark.sanity
def test_products_require_authentication(
    anon_api: ApiSession, product_factory: ProductFactory
) -> None:
    _, created = product_factory()

    for response in (
        anon_api.products.list(),
        anon_api.products.get(created["id"]),
        anon_api.products.delete(created["id"]),
    ):
        expect_api(response).is_error(401, "not_authenticated")


@pytest.mark.regression
def test_deleted_product_id_is_never_reused(
    user_api: ApiSession, backdoor: Backdoor, cleanup: CleanupRegistry
) -> None:
    """Regression for a real defect: SQLite reused the id of a deleted (newest) row, so a
    stale id silently addressed a different product. Found via a flaky parallel test."""
    first = expect_api(user_api.products.create(build_product())).has_status(201).parse(Product)
    expect_api(user_api.products.delete(first.id)).has_status(204)

    second = expect_api(user_api.products.create(build_product())).has_status(201).parse(Product)
    cleanup.add(f"delete product {second.sku}", backdoor.delete_product, second.id)

    assert second.id > first.id
    expect_api(user_api.products.get(first.id)).is_error(404)
