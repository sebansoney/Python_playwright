"""Login and registration pages."""

from __future__ import annotations

from playwright.sync_api import Page

from framework.components.form import Form
from framework.data.factories import UserData
from framework.pages.base_page import BasePage
from framework.pages.dashboard_page import DashboardPage
from framework.reporting.allure_helpers import step_method


class LoginPage(BasePage):
    PATH = "/login"
    TITLE = "Log in"

    def __init__(self, page: Page) -> None:
        super().__init__(page)
        self.form = Form(page.get_by_test_id("login-form"))
        self.error_alert = page.get_by_role("alert")
        self.register_link = page.get_by_role("link", name="Create an account")

    @step_method("Log in as {email}")
    def login(self, email: str, password: str) -> None:
        """Submit credentials. Does not assume success - the test decides."""
        self.form.fill("Email", email).fill("Password", password).submit("Log in")

    def login_as(self, email: str, password: str) -> DashboardPage:
        self.login(email, password)
        return DashboardPage(self.page).expect_loaded()


class RegisterPage(BasePage):
    PATH = "/register"
    TITLE = "Create an account"

    def __init__(self, page: Page) -> None:
        super().__init__(page)
        self.form = Form(page.get_by_test_id("register-form"))

    @step_method("Register new account {user.email}")
    def register(self, user: UserData, confirm_password: str | None = None) -> None:
        (
            self.form.fill("Full name", user.full_name)
            .fill("Email", user.email)
            .fill("Password", user.password)
            .fill(
                "Confirm password", user.password if confirm_password is None else confirm_password
            )
            .submit("Register")
        )
