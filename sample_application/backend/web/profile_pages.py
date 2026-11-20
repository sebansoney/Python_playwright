from fastapi import APIRouter, Request, UploadFile
from fastapi.responses import Response

from sample_application.backend import repository as repo
from sample_application.backend.deps import DbSession
from sample_application.backend.errors import AppError
from sample_application.backend.schemas import PasswordChange, ProfileUpdate
from sample_application.backend.validation import parse_form
from sample_application.backend.web.common import WebUser, redirect, render

router = APIRouter(prefix="/profile")


def _page(request: Request, user, **extra: object) -> Response:  # type: ignore[no-untyped-def]
    ctx = {
        "form": {"full_name": user.full_name, "phone": user.phone or ""},
        "errors": {},
        "pw_errors": {},
        "avatar_error": None,
    }
    ctx.update(extra)
    status = 400 if any(extra.get(k) for k in ("errors", "pw_errors", "avatar_error")) else 200
    return render(request, "profile.html", ctx, status_code=status)


@router.get("")
def profile(request: Request, user: WebUser) -> Response:
    return _page(request, user)


@router.post("")
async def profile_update(request: Request, db: DbSession, user: WebUser) -> Response:
    form = await request.form()
    data, errors = parse_form(ProfileUpdate, form, ("full_name", "phone"))
    if data:
        repo.update_user(db, user, data.model_dump(), acting=user)
        return redirect("/profile", flash="profile_updated")
    values = {k: str(form.get(k, "")) for k in ("full_name", "phone")}
    return _page(request, user, form=values, errors=errors)


@router.post("/password")
async def password_change(request: Request, db: DbSession, user: WebUser) -> Response:
    form = await request.form()
    data, errors = parse_form(PasswordChange, form, ("current_password", "new_password"))
    confirm = str(form.get("confirm_password", ""))
    if not confirm:
        errors["confirm_password"] = "Confirm password is required"
    elif confirm != str(form.get("new_password", "")):
        errors["confirm_password"] = "Passwords do not match"
    if data and not errors:
        try:
            repo.change_password(db, user, data.current_password, data.new_password)
        except AppError as exc:
            errors["current_password"] = str(exc.detail)
        else:
            return redirect("/profile", flash="password_changed")
    return _page(request, user, pw_errors=errors)


@router.post("/avatar")
async def avatar_upload(
    request: Request, db: DbSession, user: WebUser, file: UploadFile | None = None
) -> Response:
    if file is None or not file.filename:
        return _page(request, user, avatar_error="Choose an image to upload")
    content = await file.read(repo.AVATAR_MAX_BYTES + 1)
    try:
        repo.set_avatar(db, user, content, file.content_type)
    except AppError as exc:
        return _page(request, user, avatar_error=str(exc.detail))
    return redirect("/profile", flash="avatar_updated")


@router.get("/avatar")
def avatar_image(user: WebUser) -> Response:
    if not user.has_avatar or user.avatar is None:
        raise AppError(404, "No avatar uploaded")
    return Response(user.avatar, media_type=user.avatar_content_type)
