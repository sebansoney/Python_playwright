"""Authentication & token handling."""

from collections.abc import Callable
from typing import Any

import pytest

from config.settings import Settings
from framework.api.auth import TokenProvider
from framework.api.clients import ApiSession
from framework.api.models import Token
from framework.assertions import expect_api
from framework.data.backdoor import Backdoor
from framework.data.cleanup import CleanupRegistry
from framework.data.factories import UserData, build_user

SessionFactory = Callable[..., ApiSession]


@pytest.mark.smoke
def test_login_returns_token_that_authenticates_requests(
    anon_api: ApiSession, api_session: SessionFactory, settings: Settings
) -> None:
    email, password = settings.credentials.require("admin")

    response = anon_api.auth.login(email, password)

    token = expect_api(response).has_status(200).matches_schema("token").parse(Token)
    assert token.user.email == email
    assert token.user.role == "admin"
    assert token.expires_in > 0
    # API chaining: use the issued token for the next call.
    me = api_session(token=token.access_token).auth.me()
    expect_api(me).has_status(200).has_json("email", email)


@pytest.mark.smoke
def test_login_with_wrong_password_is_rejected(anon_api: ApiSession, settings: Settings) -> None:
    email, _ = settings.credentials.require("admin")

    response = anon_api.auth.login(email, "Wrong-Password-1")

    expect_api(response).is_error(401, "invalid_credentials").has_detail(
        "Invalid email or password"
    )


@pytest.mark.regression
def test_unknown_email_gets_same_message_as_wrong_password(anon_api: ApiSession) -> None:
    """No user enumeration: the API must not reveal whether an email exists."""
    response = anon_api.auth.login("nobody.here@example.test", "Whatever-Pass-1")

    expect_api(response).is_error(401, "invalid_credentials").has_detail(
        "Invalid email or password"
    )


@pytest.mark.regression
@pytest.mark.parametrize(
    ("email", "password", "missing"),
    [
        (None, None, ("email", "password")),
        ("admin@example.test", None, ("password",)),
        (None, "Some-Pass-1", ("email",)),
        ("", "", ("email", "password")),
    ],
    ids=["both-missing", "password-missing", "email-missing", "both-empty"],
)
def test_login_missing_mandatory_fields(
    anon_api: ApiSession, email: str | None, password: str | None, missing: tuple[str, ...]
) -> None:
    response = anon_api.auth.login(email, password)

    check = expect_api(response).is_error(422, "validation_error")
    check.has_field_errors_exactly(*missing)
    for field in missing:
        check.has_field_error(field, f"{field.capitalize()} is required")


@pytest.mark.regression
def test_disabled_account_cannot_log_in(anon_api: ApiSession, settings: Settings) -> None:
    _, password = settings.credentials.require("user")  # seeded with the user password

    response = anon_api.auth.login("disabled.user@example.test", password)

    expect_api(response).is_error(403, "account_disabled").has_detail("Account is disabled")


@pytest.mark.smoke
def test_request_without_token_is_unauthorized(anon_api: ApiSession) -> None:
    response = anon_api.users.list()

    expect_api(response).is_error(401, "not_authenticated").has_header("WWW-Authenticate", "Bearer")


@pytest.mark.regression
@pytest.mark.parametrize("kind", ["garbage", "tampered-signature", "empty-parts"])
def test_invalid_token_is_rejected(
    api_session: SessionFactory, token_provider: TokenProvider, settings: Settings, kind: str
) -> None:
    real = token_provider.token(*settings.credentials.require("admin"))
    token = {
        "garbage": "not-a-jwt",
        "tampered-signature": real[:-4] + ("AAAA" if not real.endswith("AAAA") else "BBBB"),
        "empty-parts": "..",
    }[kind]

    response = api_session(token=token).products.list()

    expect_api(response).is_error(401, "invalid_token").has_detail("Invalid or expired token")


@pytest.mark.regression
def test_register_then_login_with_new_account(
    anon_api: ApiSession, backdoor: Backdoor, cleanup: CleanupRegistry
) -> None:
    user = build_user()
    payload = {"email": user.email, "full_name": user.full_name, "password": user.password}

    created = anon_api.auth.register(payload)
    cleanup.add(f"delete user {user.email}", backdoor.delete_user_by_email, user.email)

    expect_api(created).has_status(201).matches_schema("user").json_contains(
        {"email": user.email, "role": "user", "is_active": True}
    )
    login = anon_api.auth.login(user.email, user.password)
    expect_api(login).has_status(200).has_json("user.id", created.json["id"])


@pytest.mark.regression
def test_register_cannot_choose_admin_role(anon_api: ApiSession) -> None:
    user = build_user()
    payload = {**user.to_api(), "role": "admin"}

    response = anon_api.auth.register(payload)

    expect_api(response).is_error(422).has_field_error("role", "Unknown field 'role'")


@pytest.mark.regression
def test_profile_password_change_flow(
    api_session: SessionFactory,
    anon_api: ApiSession,
    user_factory: Callable[..., tuple[UserData, dict[str, Any]]],
) -> None:
    """Chained flow: update profile -> change password -> old fails, new works."""
    user, _ = user_factory()
    me = api_session(email=user.email, password=user.password)
    new_password = "Changed-Pass-42"

    expect_api(
        me.profile.update({"full_name": "Renamed Person", "phone": "+1 555 0100"})
    ).has_status(200).json_contains({"full_name": "Renamed Person", "phone": "+1 555 0100"})
    expect_api(me.profile.change_password("wrong-current-1", new_password)).is_error(
        400, "wrong_password"
    )
    expect_api(me.profile.change_password(user.password, new_password)).has_status(
        204
    ).has_empty_body()

    expect_api(anon_api.auth.login(user.email, user.password)).is_error(401, "invalid_credentials")
    expect_api(anon_api.auth.login(user.email, new_password)).has_status(200)
