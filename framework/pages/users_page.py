"""User management (admin)."""

from __future__ import annotations

from playwright.sync_api import Locator, Page, expect

from framework.components.data_table import DataTable
from framework.components.dialogs import NextDialog
from framework.components.form import Form
from framework.data.factories import UserData
from framework.pages.base_page import BasePage
from framework.reporting.allure_helpers import step_method


class UsersPage(BasePage):
    PATH = "/users"
    TITLE = "Users"

    def __init__(self, page: Page) -> None:
        super().__init__(page)
        self.search_box = page.get_by_role("searchbox", name="Search users")
        self.results_count = page.get_by_test_id("results-count")
        self.table = DataTable(page.get_by_role("table"))
        self.empty_state = page.get_by_test_id("empty-state")

    @step_method("Search users for '{text}'")
    def search(self, text: str) -> UsersPage:
        self.search_box.fill(text)
        self.submit_and_wait(
            lambda: self.page.get_by_role("button", name="Search", exact=True).click()
        )
        return self

    def row(self, email: str) -> Locator:
        return self.table.row_with(email)

    @step_method("Open 'Add user' form")
    def open_add_user(self) -> UserFormPage:
        self.page.get_by_role("link", name="Add user").click()
        return UserFormPage(self.page, editing=False).expect_loaded()

    @step_method("Open edit form of user {email}")
    def open_edit(self, email: str) -> UserFormPage:
        self.row(email).get_by_role("link", name="Edit").click()
        return UserFormPage(self.page, editing=True).expect_loaded()

    @step_method("Delete user {email} (accept dialog: {confirm})")
    def delete(self, email: str, confirm: bool = True) -> NextDialog:
        dialog = NextDialog(self.page, accept=confirm)
        self.row(email).get_by_role("button", name="Delete").click()
        return dialog


class UserFormPage(BasePage):
    PATH = "/users"

    def __init__(self, page: Page, editing: bool) -> None:
        super().__init__(page)
        self.editing = editing
        self.TITLE = "Edit user" if editing else "Add user"
        self.form = Form(page.get_by_test_id("user-form"))

    def expect_loaded(self) -> UserFormPage:
        expect(self.heading).to_have_text(self.TITLE)
        return self

    @step_method("Fill user form ({user.email}, role {user.role})")
    def fill(self, user: UserData) -> UserFormPage:
        self.form.fill("Full name", user.full_name).fill("Email", user.email)
        if not self.editing:
            self.form.fill("Password", user.password)
        self.form.fill("Phone", user.phone).select("Role", user.role)
        return self

    @step_method("Set 'Active' = {active}")
    def set_active(self, active: bool) -> UserFormPage:
        self.form.set_checked("Active", active)
        return self

    @step_method("Save user form")
    def save(self) -> None:
        self.form.submit("Save changes" if self.editing else "Create user")
