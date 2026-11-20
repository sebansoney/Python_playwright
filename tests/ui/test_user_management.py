"""User management (admin only)."""

from collections.abc import Callable
from typing import Any

import pytest
from playwright.sync_api import Page, expect

from framework.data.backdoor import Backdoor
from framework.data.cleanup import CleanupRegistry
from framework.data.factories import UserData, build_user
from framework.pages import UsersPage

UserFactory = Callable[..., tuple[UserData, dict[str, Any]]]


@pytest.mark.smoke
def test_admin_creates_user(admin_page: Page, backdoor: Backdoor, cleanup: CleanupRegistry) -> None:
    user = build_user(role="user", phone="+44 20 7946 0000")
    cleanup.add(f"delete user {user.email}", backdoor.delete_user_by_email, user.email)
    users = UsersPage(admin_page).open()

    users.open_add_user().fill(user).save()

    users.expect_loaded()
    users.flash.expect_text("User created successfully.")
    users.search(user.email)
    row = users.row(user.email)
    expect(row).to_have_count(1)
    expect(users.table.cell(row, "Name")).to_have_text(user.full_name)
    expect(users.table.cell(row, "Role")).to_have_text("user")
    expect(users.table.cell(row, "Status")).to_have_text("Active")


@pytest.mark.regression
def test_admin_edits_user_role_and_deactivates(
    admin_page: Page, user_factory: UserFactory, backdoor: Backdoor
) -> None:
    user, created = user_factory(role="user")
    users = UsersPage(admin_page).open().search(user.email)

    form = users.open_edit(user.email)
    form.fill(
        UserData(full_name=f"{user.full_name} Edited", email=user.email, password="", role="admin")
    )
    form.set_active(False).save()

    users.flash.expect_text("User updated successfully.")
    users.search(user.email)
    row = users.row(user.email)
    expect(users.table.cell(row, "Name")).to_have_text(f"{user.full_name} Edited")
    expect(users.table.cell(row, "Role")).to_have_text("admin")
    expect(users.table.cell(row, "Status")).to_have_text("Inactive")
    # Cross-check the stored state (not only what the page shows).
    stored = backdoor.get_user(created["id"])
    assert (stored["role"], stored["is_active"]) == ("admin", False)


@pytest.mark.regression
def test_admin_deletes_user_after_confirmation(admin_page: Page, user_factory: UserFactory) -> None:
    user, _ = user_factory()
    users = UsersPage(admin_page).open().search(user.email)

    dialog = users.delete(user.email, confirm=True)

    users.flash.expect_text("User deleted successfully.")
    assert dialog.message == f"Delete user {user.full_name}? This cannot be undone."
    users.search(user.email)
    expect(users.empty_state).to_be_visible()


@pytest.mark.regression
def test_admin_create_user_validation(admin_page: Page) -> None:
    form = UsersPage(admin_page).open().open_add_user()

    form.save()  # everything empty

    form.form.expect_error("Full name", "Full name is required")
    form.form.expect_error("Email", "Email is required")
    form.form.expect_error("Password", "Password is required")


@pytest.mark.sanity
def test_standard_user_cannot_access_user_management(user_page: Page) -> None:
    response = user_page.goto(UsersPage.PATH)

    assert response is not None
    assert response.status == 403
    expect(user_page.get_by_role("heading", level=1)).to_have_text("Access denied")
    expect(UsersPage(user_page).nav.link("Users")).to_have_count(0)
