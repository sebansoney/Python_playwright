"""Users across layers: API <-> UI."""

from collections.abc import Callable
from typing import Any

import pytest
from playwright.sync_api import Page, expect

from framework.api.clients import ApiSession
from framework.api.models import Page as ApiPage
from framework.api.models import Token, User
from framework.assertions import expect_api
from framework.data.backdoor import Backdoor
from framework.data.cleanup import CleanupRegistry
from framework.data.factories import UserData, build_user
from framework.pages import LoginPage, RegisterPage, UsersPage

UserFactory = Callable[..., tuple[UserData, dict[str, Any]]]


@pytest.mark.smoke
def test_api_created_user_is_visible_in_ui_and_can_log_in(
    api: ApiSession, admin_page: Page, page: Page, cleanup: CleanupRegistry, backdoor: Backdoor
) -> None:
    # Arrange + Act (API): create the user through the public API.
    user = build_user(phone="+44 20 7946 0123")
    created = expect_api(api.users.create(user)).has_status(201).parse(User)
    cleanup.add(f"delete user {user.email}", backdoor.delete_user, created.id)

    # Assert (UI, admin view): the user is listed with the API's values.
    users = UsersPage(admin_page).open().search(user.email)
    row = users.row(user.email)
    expect(users.table.cell(row, "Name")).to_have_text(user.full_name)
    expect(users.table.cell(row, "Role")).to_have_text("user")
    expect(users.table.cell(row, "Status")).to_have_text("Active")

    # Assert (UI, the user's own view): the API-set password works in the login form.
    dashboard = LoginPage(page).open().login_as(user.email, user.password)
    expect(dashboard.welcome).to_have_text(f"Welcome, {user.full_name}!")


@pytest.mark.smoke
def test_api_user_update_is_reflected_in_ui(
    api: ApiSession, admin_page: Page, page: Page, user_factory: UserFactory
) -> None:
    user, created = user_factory()
    new_name = f"{user.full_name} Promoted"

    expect_api(
        api.users.update(created["id"], {"full_name": new_name, "role": "admin"})
    ).has_status(200)

    users = UsersPage(admin_page).open().search(user.email)
    row = users.row(user.email)
    expect(users.table.cell(row, "Name")).to_have_text(new_name)
    expect(users.table.cell(row, "Role")).to_have_text("admin")

    # Deactivate via API -> the UI refuses the login with the documented message.
    expect_api(api.users.update(created["id"], {"is_active": False})).has_status(200)
    login = LoginPage(page).open()
    login.login(user.email, user.password)
    expect(login.error_alert).to_have_text("Account is disabled")
    users.search(user.email)
    expect(users.table.cell(users.row(user.email), "Status")).to_have_text("Inactive")


@pytest.mark.regression
def test_ui_registration_creates_account_usable_via_api(
    page: Page, anon_api: ApiSession, api: ApiSession, backdoor: Backdoor, cleanup: CleanupRegistry
) -> None:
    user = build_user()
    cleanup.add(f"delete user {user.email}", backdoor.delete_user_by_email, user.email)

    RegisterPage(page).open().register(user)
    LoginPage(page).expect_loaded().flash.expect_text("Registration successful. Please log in.")

    token = expect_api(anon_api.auth.login(user.email, user.password)).has_status(200).parse(Token)
    assert (token.user.email, token.user.full_name, token.user.role) == (
        user.email,
        user.full_name,
        "user",
    )
    found = expect_api(api.users.list(q=user.email)).has_status(200).parse(ApiPage[User])
    assert [u.id for u in found.items] == [token.user.id]


@pytest.mark.smoke
def test_ui_user_delete_is_verified_via_api(
    api: ApiSession, admin_page: Page, user_factory: UserFactory
) -> None:
    user, created = user_factory()
    expect_api(api.users.get(created["id"])).has_status(200)  # precondition visible via API

    users = UsersPage(admin_page).open().search(user.email)
    users.delete(user.email, confirm=True)
    users.flash.expect_text("User deleted successfully.")

    expect_api(api.users.get(created["id"])).is_error(404, "not_found").has_detail("User not found")
    found = expect_api(api.users.list(q=user.email)).has_status(200).parse(ApiPage[User])
    assert found.items == []
