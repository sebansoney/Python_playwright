from fastapi import APIRouter, Request
from fastapi.responses import Response

from sample_application.backend import repository as repo
from sample_application.backend.api.auth import set_auth_cookie
from sample_application.backend.config import config
from sample_application.backend.deps import DbSession, OptionalUser
from sample_application.backend.errors import AppError
from sample_application.backend.schemas import LoginRequest, RegisterRequest, UserCreate
from sample_application.backend.security import create_access_token
from sample_application.backend.validation import parse_form
from sample_application.backend.web.common import redirect, render, safe_next

router = APIRouter()


@router.get("/")
def home(user: OptionalUser) -> Response:
    return redirect("/dashboard" if user else "/login")


@router.get("/login")
def login_page(request: Request, user: OptionalUser) -> Response:
    if user:
        return redirect("/dashboard")
    return render(
        request,
        "login.html",
        {"form": {}, "errors": {}, "next": request.query_params.get("next", "")},
    )


@router.post("/login")
async def login_submit(request: Request, db: DbSession) -> Response:
    form = await request.form()
    values = {"email": str(form.get("email", "")).strip()}
    next_url = str(form.get("next", ""))
    data, errors = parse_form(LoginRequest, form, ("email", "password"))
    error_message = None
    if data:
        try:
            user = repo.authenticate(db, data.email, data.password)
        except AppError as exc:
            error_message = str(exc.detail)
        else:
            token, ttl = create_access_token(user.id, user.role)
            response = redirect(safe_next(next_url))
            set_auth_cookie(response, token, ttl)
            return response
    return render(
        request,
        "login.html",
        {"form": values, "errors": errors, "error_message": error_message, "next": next_url},
        status_code=400 if errors else 401,
    )


@router.post("/logout")
def logout() -> Response:
    response = redirect("/login", flash="logged_out")
    response.delete_cookie(config.cookie_name, path="/")
    return response


@router.get("/register")
def register_page(request: Request) -> Response:
    return render(request, "register.html", {"form": {}, "errors": {}})


@router.post("/register")
async def register_submit(request: Request, db: DbSession) -> Response:
    form = await request.form()
    values = {k: str(form.get(k, "")).strip() for k in ("full_name", "email")}
    data, errors = parse_form(RegisterRequest, form, ("full_name", "email", "password"))
    confirm = str(form.get("confirm_password", ""))
    if not confirm:
        errors["confirm_password"] = "Confirm password is required"
    elif confirm != str(form.get("password", "")):
        errors["confirm_password"] = "Passwords do not match"
    if data and not errors:
        try:
            repo.create_user(db, UserCreate(**data.model_dump(), role="user"))
        except AppError as exc:
            errors["email"] = str(exc.detail)
        else:
            return redirect("/login", flash="registered")
    return render(request, "register.html", {"form": values, "errors": errors}, status_code=400)
