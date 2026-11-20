"""Users resource: CRUD, validation, boundaries, authorization."""

import math
from collections.abc import Callable
from typing import Any

import pytest

from framework.api.clients import ApiSession
from framework.api.models import Page, User
from framework.assertions import expect_api
from framework.data.backdoor import Backdoor
from framework.data.cleanup import CleanupRegistry
from framework.data.factories import UserData, build_user, token

UserFactory = Callable[..., tuple[UserData, dict[str, Any]]]


@pytest.fixture
def new_user_payload(backdoor: Backdoor, cleanup: CleanupRegistry) -> dict[str, Any]:
    """Valid create-user payload; whatever gets created from it is removed afterwards."""
    user = build_user()
    cleanup.add(f"delete user {user.email}", backdoor.delete_user_by_email, user.email)
    return user.to_api()


# ----------------------------------------------------------------- read
@pytest.mark.smoke
def test_list_users_matches_contract_and_paginates(api: ApiSession) -> None:
    response = api.users.list(page=1, size=2)

    page = expect_api(response).has_status(200).matches_schema("user_page").parse(Page[User])
    assert (page.page, page.size) == (1, 2)
    assert len(page.items) <= 2
    assert page.total >= 5  # seeded users
    assert page.pages == math.ceil(page.total / 2)


@pytest.mark.regression
def test_search_and_filter_users(api: ApiSession) -> None:
    by_email = api.users.list(q="grace.hopper").json
    assert [u["email"] for u in by_email["items"]] == ["grace.hopper@example.test"]

    admins = expect_api(api.users.list(role="admin", size=100)).has_status(200).parse(Page[User])
    assert admins.items
    assert {u.role for u in admins.items} == {"admin"}


@pytest.mark.regression
def test_get_user_by_id(api: ApiSession, user_factory: UserFactory) -> None:
    user, created = user_factory(phone="+44 20 7946 0001")

    response = api.users.get(created["id"])

    expect_api(response).has_status(200).matches_schema("user").json_contains(
        {"id": created["id"], "email": user.email, "full_name": user.full_name, "phone": user.phone}
    )


# --------------------------------------------------------------- create
@pytest.mark.smoke
def test_create_user(api: ApiSession, new_user_payload: dict[str, Any]) -> None:
    payload = {**new_user_payload, "email": new_user_payload["email"].upper()}

    response = api.users.create(payload)

    user = expect_api(response).has_status(201).matches_schema("user").parse(User)
    expect_api(response).has_header("Location", f"/api/v1/users/{user.id}")
    assert user.email == new_user_payload["email"]  # stored lower-case
    assert (user.role, user.is_active, user.has_avatar) == ("user", True, False)
    assert "password" not in response.json  # never echoed back


@pytest.mark.regression
def test_create_user_with_duplicate_email_conflicts(
    api: ApiSession, user_factory: UserFactory
) -> None:
    existing, _ = user_factory()
    duplicate = build_user(email=existing.email.upper())  # case-insensitive uniqueness

    response = api.users.create(duplicate)

    expect_api(response).is_error(409, "duplicate_email").has_detail(
        "A user with this email already exists"
    )


@pytest.mark.regression
@pytest.mark.parametrize(
    ("field", "message"),
    [
        ("email", "Email is required"),
        ("full_name", "Full name is required"),
        ("password", "Password is required"),
    ],
)
def test_create_user_missing_mandatory_field(
    api: ApiSession, new_user_payload: dict[str, Any], field: str, message: str
) -> None:
    del new_user_payload[field]

    response = api.users.create(new_user_payload)

    expect_api(response).is_error(422, "validation_error").has_field_errors_exactly(
        field
    ).has_field_error(field, message)


@pytest.mark.regression
@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("email", "not-an-email", "Enter a valid email address"),
        (
            "phone",
            "call me",
            "Enter a valid phone number (digits, spaces, dashes, optional leading +)",
        ),
        ("role", "superuser", None),
        ("full_name", 12345, "Full name has an invalid type"),
        ("password", "lettersonly", "Password must contain at least one letter and one number"),
        ("nickname", "Bob", "Unknown field 'nickname'"),
    ],
    ids=["bad-email", "bad-phone", "unknown-role", "wrong-type", "weak-password", "unknown-field"],
)
def test_create_user_invalid_payload(
    api: ApiSession, new_user_payload: dict[str, Any], field: str, value: Any, message: str | None
) -> None:
    new_user_payload[field] = value

    response = api.users.create(new_user_payload)

    expect_api(response).is_error(422, "validation_error").has_field_error(field, message)
    if field == "role":  # message lists the allowed values; check its stable prefix
        assert response.json["errors"][0]["message"].startswith("Role must be one of")


@pytest.mark.regression
@pytest.mark.parametrize(
    ("length", "status"), [(1, 422), (2, 201), (60, 201), (61, 422)], ids=lambda v: str(v)
)
def test_full_name_length_boundaries(
    api: ApiSession, new_user_payload: dict[str, Any], length: int, status: int
) -> None:
    new_user_payload["full_name"] = "N" * length

    response = api.users.create(new_user_payload)

    expect_api(response).has_status(status)


@pytest.mark.regression
@pytest.mark.parametrize(
    ("length", "status"), [(7, 422), (8, 201), (64, 201), (65, 422)], ids=lambda v: str(v)
)
def test_password_length_boundaries(
    api: ApiSession, new_user_payload: dict[str, Any], length: int, status: int
) -> None:
    new_user_payload["password"] = ("a1" * 40)[:length]  # letters + digits, exact length

    response = api.users.create(new_user_payload)

    expect_api(response).has_status(status)


# --------------------------------------------------------------- update
@pytest.mark.regression
def test_replace_user_with_put(api: ApiSession, user_factory: UserFactory) -> None:
    _user, created = user_factory()
    replacement = {
        "email": f"replaced.{token()}@example.test",
        "full_name": "Replaced Name",
        "role": "admin",
        "is_active": False,
        "phone": "+1 202 555 0147",
    }

    response = api.users.replace(created["id"], replacement)

    expect_api(response).has_status(200).matches_schema("user").json_contains(replacement)
    expect_api(api.users.get(created["id"])).json_contains(replacement)  # persisted


@pytest.mark.regression
def test_put_requires_every_field(api: ApiSession, user_factory: UserFactory) -> None:
    user, created = user_factory()

    response = api.users.replace(
        created["id"], {"email": user.email, "full_name": "X Y", "role": "user"}
    )

    expect_api(response).is_error(422).has_field_errors_exactly("is_active").has_field_error(
        "is_active", "Active is required"
    )


@pytest.mark.regression
def test_patch_user_changes_only_given_fields(api: ApiSession, user_factory: UserFactory) -> None:
    user, created = user_factory()

    response = api.users.update(created["id"], {"phone": "+49 30 1234567"})

    expect_api(response).has_status(200).json_contains(
        {
            "phone": "+49 30 1234567",
            "email": user.email,
            "full_name": user.full_name,
            "role": "user",
        }
    )
    assert response.json["updated_at"] >= created["updated_at"]


@pytest.mark.regression
def test_empty_patch_is_rejected(api: ApiSession, user_factory: UserFactory) -> None:
    _, created = user_factory()

    expect_api(api.users.update(created["id"], {})).is_error(400, "empty_patch")


# --------------------------------------------------------------- delete
@pytest.mark.smoke
def test_delete_user_then_it_is_gone(api: ApiSession, user_factory: UserFactory) -> None:
    _, created = user_factory()

    expect_api(api.users.delete(created["id"])).has_status(204).has_empty_body()

    expect_api(api.users.get(created["id"])).is_error(404, "not_found").has_detail("User not found")
    expect_api(api.users.delete(created["id"])).is_error(404)  # not idempotent-success


@pytest.mark.regression
def test_admin_cannot_delete_own_account(api: ApiSession) -> None:
    me = api.auth.me().json

    expect_api(api.users.delete(me["id"])).is_error(400, "self_delete")


# ------------------------------------------------------ invalid ids / authz
@pytest.mark.regression
@pytest.mark.parametrize(
    ("user_id", "status"), [(999_999_999, 404), (0, 404), (-1, 404), ("abc", 422), ("1.5", 422)]
)
def test_invalid_user_id(api: ApiSession, user_id: Any, status: int) -> None:
    response = api.users.get(user_id)

    if status == 404:
        expect_api(response).is_error(404, "not_found").has_detail("User not found")
    else:
        expect_api(response).is_error(422).has_field_error(
            "user_id", "User id must be a whole number"
        )


@pytest.mark.sanity
def test_standard_user_permissions(user_api: ApiSession, api: ApiSession) -> None:
    own_id = user_api.auth.me().json["id"]
    admin_id = api.auth.me().json["id"]

    expect_api(user_api.users.list()).is_error(403, "forbidden").has_detail("Admin role required")
    expect_api(user_api.users.get(own_id)).has_status(200)
    expect_api(user_api.users.get(admin_id)).is_error(403).has_detail(
        "You can only view your own account"
    )
    expect_api(user_api.users.delete(admin_id)).is_error(403)
