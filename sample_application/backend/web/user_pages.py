"""User management pages (admin only)."""

from typing import Annotated

from fastapi import APIRouter, Query, Request
from fastapi.responses import Response

from sample_application.backend import repository as repo
from sample_application.backend.deps import DbSession
from sample_application.backend.errors import AppError
from sample_application.backend.schemas import UserCreate, UserUpdate
from sample_application.backend.validation import parse_form
from sample_application.backend.web.common import WebAdmin, redirect, render

router = APIRouter(prefix="/users")

PAGE_SIZE = 10
_CREATE_FIELDS = ("full_name", "email", "password", "role", "phone")
_EDIT_FIELDS = ("full_name", "email", "role", "phone")


@router.get("")
def users_list(
    request: Request,
    db: DbSession,
    _admin: WebAdmin,
    q: Annotated[str | None, Query(max_length=100)] = None,
    page: Annotated[int, Query(ge=1)] = 1,
) -> Response:
    users, total = repo.list_users(db, q=q, page=page, size=PAGE_SIZE)
    pages = max(1, -(-total // PAGE_SIZE))
    return render(
        request,
        "users.html",
        {"users": users, "total": total, "q": q or "", "page": page, "pages": pages},
    )


@router.get("/new")
def user_new(request: Request, _admin: WebAdmin) -> Response:
    return render(request, "user_form.html", {"form": {"role": "user"}, "errors": {}, "user": None})


@router.post("/new")
async def user_create(request: Request, db: DbSession, _admin: WebAdmin) -> Response:
    form = await request.form()
    data, errors = parse_form(UserCreate, form, _CREATE_FIELDS)
    if data:
        try:
            repo.create_user(db, data)
        except AppError as exc:
            errors["email"] = str(exc.detail)
        else:
            return redirect("/users", flash="user_created")
    values = {k: str(form.get(k, "")) for k in _CREATE_FIELDS if k != "password"}
    return render(request, "user_form.html", {"form": values, "errors": errors, "user": None}, 400)


@router.get("/{user_id}/edit")
def user_edit(user_id: int, request: Request, db: DbSession, _admin: WebAdmin) -> Response:
    user = repo.get_user(db, user_id)
    form = {
        "full_name": user.full_name,
        "email": user.email,
        "role": user.role,
        "phone": user.phone or "",
        "is_active": user.is_active,
    }
    return render(request, "user_form.html", {"form": form, "errors": {}, "user": user})


@router.post("/{user_id}/edit")
async def user_update(user_id: int, request: Request, db: DbSession, admin: WebAdmin) -> Response:
    user = repo.get_user(db, user_id)
    form = await request.form()
    payload = {k: form[k] for k in _EDIT_FIELDS if k in form}
    payload["is_active"] = "is_active" in form  # unchecked checkboxes are not submitted
    data, errors = parse_form(UserUpdate, payload, (*_EDIT_FIELDS, "is_active"))
    if data:
        try:
            repo.update_user(db, user, data.model_dump(), acting=admin)
        except AppError as exc:
            errors["form"] = str(exc.detail)
        else:
            return redirect("/users", flash="user_updated")
    values = {k: str(form.get(k, "")) for k in _EDIT_FIELDS} | {"is_active": "is_active" in form}
    return render(request, "user_form.html", {"form": values, "errors": errors, "user": user}, 400)


@router.post("/{user_id}/delete")
def user_delete(user_id: int, db: DbSession, admin: WebAdmin) -> Response:
    repo.delete_user(db, repo.get_user(db, user_id), acting=admin)
    return redirect("/users", flash="user_deleted")
