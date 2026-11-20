"""FastAPI dependencies: DB session and authentication.

A request is authenticated by EITHER
  * ``Authorization: Bearer <jwt>``  (API clients), or
  * the HTTP-only ``access_token`` cookie holding the same JWT (browser).
That lets a test log in via the API and hand the token to the browser.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from sample_application.backend.config import config
from sample_application.backend.database import get_db
from sample_application.backend.errors import AppError
from sample_application.backend.models import User
from sample_application.backend.security import decode_access_token

DbSession = Annotated[Session, Depends(get_db)]


def _token_from(request: Request) -> str | None:
    header = request.headers.get("Authorization", "")
    scheme, _, value = header.partition(" ")
    if scheme.lower() == "bearer" and value:
        return value.strip()
    return request.cookies.get(config.cookie_name)


def get_optional_user(request: Request, db: DbSession) -> User | None:
    token = _token_from(request)
    payload = decode_access_token(token) if token else None
    if not payload:
        return None
    user = db.get(User, int(payload["sub"]))
    if user is None or not user.is_active:
        return None
    request.state.user = user
    return user


def get_current_user(
    request: Request, user: Annotated[User | None, Depends(get_optional_user)]
) -> User:
    if user is None:
        has_token = bool(_token_from(request))
        raise AppError(
            401,
            "Invalid or expired token" if has_token else "Not authenticated",
            code="invalid_token" if has_token else "not_authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


def require_admin(user: Annotated[User, Depends(get_current_user)]) -> User:
    if user.role != "admin":
        raise AppError(403, "Admin role required")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
AdminUser = Annotated[User, Depends(require_admin)]
OptionalUser = Annotated[User | None, Depends(get_optional_user)]
