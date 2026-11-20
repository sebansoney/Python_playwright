"""Shared helpers for server-rendered pages."""

from __future__ import annotations

from typing import Annotated, Any
from urllib.parse import urlencode

from fastapi import Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from sample_application.backend.config import FRONTEND_DIR
from sample_application.backend.deps import OptionalUser
from sample_application.backend.errors import AppError
from sample_application.backend.models import User
from sample_application.backend.schemas import CATEGORIES

templates = Jinja2Templates(directory=FRONTEND_DIR / "templates")

# Flash messages are referenced by a fixed key in the redirect URL (?flash=key),
# never by free text, so nothing user-controlled is reflected into the page.
FLASH_MESSAGES: dict[str, tuple[str, str]] = {
    "registered": ("success", "Registration successful. Please log in."),
    "logged_out": ("info", "You have been logged out."),
    "user_created": ("success", "User created successfully."),
    "user_updated": ("success", "User updated successfully."),
    "user_deleted": ("success", "User deleted successfully."),
    "product_created": ("success", "Product created successfully."),
    "product_updated": ("success", "Product updated successfully."),
    "product_deleted": ("success", "Product deleted successfully."),
    "profile_updated": ("success", "Profile updated successfully."),
    "password_changed": ("success", "Password changed successfully."),
    "avatar_updated": ("success", "Profile picture updated."),
}


def web_user(user: OptionalUser) -> User:
    """Page dependency: anonymous visitors are redirected to /login (see errors.py)."""
    if user is None:
        raise AppError(401, "Login required")
    return user


def web_admin(user: Annotated[User, Depends(web_user)]) -> User:
    if user.role != "admin":
        raise AppError(403, "You do not have permission to view this page.")
    return user


WebUser = Annotated[User, Depends(web_user)]
WebAdmin = Annotated[User, Depends(web_admin)]


def render(
    request: Request, template: str, context: dict[str, Any] | None = None, status_code: int = 200
) -> HTMLResponse:
    flash = FLASH_MESSAGES.get(request.query_params.get("flash", ""))
    ctx = {
        "current_user": getattr(request.state, "user", None),
        "flash": flash,
        "categories": CATEGORIES,
        **(context or {}),
    }
    return templates.TemplateResponse(request, template, ctx, status_code=status_code)


def render_error(request: Request, status_code: int, message: str) -> HTMLResponse:
    titles = {403: "Access denied", 404: "Page not found"}
    return render(
        request,
        "error.html",
        {
            "status_code": status_code,
            "title": titles.get(status_code, "Something went wrong"),
            "message": message,
        },
        status_code=status_code,
    )


def redirect(url: str, flash: str | None = None, **params: Any) -> RedirectResponse:
    query = {k: v for k, v in params.items() if v not in (None, "")}
    if flash:
        query["flash"] = flash
    sep = "&" if "?" in url else "?"
    return RedirectResponse(url + (sep + urlencode(query) if query else ""), status_code=303)


def safe_next(target: str | None) -> str:
    """Only allow local redirects after login (prevents open-redirect)."""
    if target and target.startswith("/") and not target.startswith("//"):
        return target
    return "/dashboard"
