from fastapi import APIRouter, Response, status

from sample_application.backend import repository as repo
from sample_application.backend.config import config
from sample_application.backend.deps import CurrentUser, DbSession
from sample_application.backend.schemas import (
    LoginRequest,
    RegisterRequest,
    TokenResponse,
    UserCreate,
    UserOut,
)
from sample_application.backend.security import create_access_token

router = APIRouter(prefix="/auth", tags=["auth"])


def set_auth_cookie(response: Response, token: str, max_age: int) -> None:
    response.set_cookie(
        config.cookie_name, token, max_age=max_age, httponly=True, samesite="lax", path="/"
    )


@router.post("/login")
def login(body: LoginRequest, db: DbSession, response: Response) -> TokenResponse:
    user = repo.authenticate(db, body.email, body.password)
    token, ttl = create_access_token(user.id, user.role)
    # Also set the cookie so a browser-shared API context is logged in too.
    set_auth_cookie(response, token, ttl)
    return TokenResponse(access_token=token, expires_in=ttl, user=UserOut.model_validate(user))


@router.post("/register", status_code=status.HTTP_201_CREATED)
def register(body: RegisterRequest, db: DbSession) -> UserOut:
    user = repo.create_user(db, UserCreate(**body.model_dump(), role="user"))
    return UserOut.model_validate(user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(response: Response) -> None:
    # JWTs are stateless; logout removes the browser cookie.
    response.delete_cookie(config.cookie_name, path="/")


@router.get("/me")
def me(user: CurrentUser) -> UserOut:
    return UserOut.model_validate(user)
