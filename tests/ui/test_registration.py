"""Self-registration."""

from collections.abc import Callable
from typing import Any

import pytest
from playwright.sync_api import Page

from framework.data.backdoor import Backdoor
from framework.data.cleanup import CleanupRegistry
from framework.data.factories import UserData, build_user
from framework.pages import LoginPage, RegisterPage


@pytest.mark.smoke
def test_new_user_can_register_and_log_in(
    page: Page, backdoor: Backdoor, cleanup: CleanupRegistry
) -> None:
    user = build_user()
    cleanup.add(f"delete user {user.email}", backdoor.delete_user_by_email, user.email)

    RegisterPage(page).open().register(user)

    login = LoginPage(page).expect_loaded()
    login.flash.expect_text("Registration successful. Please log in.")
    dashboard = login.login_as(user.email, user.password)
    dashboard.nav.expect_logged_in_as(user.full_name)


@pytest.mark.regression
@pytest.mark.parametrize(
    ("field", "overrides", "confirm", "message"),
    [
        ("Confirm password", {}, "Different-Pass-1", "Passwords do not match"),
        ("Password", {"password": "short1"}, None, "Password must be at least 8 characters"),
        (
            "Password",
            {"password": "lettersonly"},
            None,
            "Password must contain at least one letter and one number",
        ),
        ("Email", {"email": "not-an-email"}, None, "Enter a valid email address"),
        ("Full name", {"full_name": "A"}, None, "Full name must be at least 2 characters"),
    ],
    ids=["password-mismatch", "password-too-short", "password-no-digit", "bad-email", "short-name"],
)
def test_registration_validation(
    page: Page, field: str, overrides: dict[str, str], confirm: str | None, message: str
) -> None:
    register = RegisterPage(page).open()

    register.register(build_user(**overrides), confirm_password=confirm)

    register.expect_loaded()  # stayed on the form
    register.form.expect_error(field, message)


@pytest.mark.regression
def test_registration_rejects_existing_email(
    page: Page, user_factory: Callable[..., tuple[UserData, Any]]
) -> None:
    existing, _ = user_factory()
    register = RegisterPage(page).open()

    register.register(build_user(email=existing.email))

    register.form.expect_error("Email", "A user with this email already exists")
