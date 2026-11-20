"""Page Object Model for the sample application."""

from framework.pages.auth_pages import LoginPage, RegisterPage
from framework.pages.base_page import BasePage
from framework.pages.dashboard_page import DashboardPage
from framework.pages.products_page import ProductDetailPage, ProductFormPage, ProductsPage
from framework.pages.profile_page import ProfilePage
from framework.pages.tools_page import ToolsPage
from framework.pages.users_page import UserFormPage, UsersPage

__all__ = [
    "BasePage",
    "DashboardPage",
    "LoginPage",
    "ProductDetailPage",
    "ProductFormPage",
    "ProductsPage",
    "ProfilePage",
    "RegisterPage",
    "ToolsPage",
    "UserFormPage",
    "UsersPage",
]
