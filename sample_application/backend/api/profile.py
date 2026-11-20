from fastapi import APIRouter, Response, UploadFile, status

from sample_application.backend import repository as repo
from sample_application.backend.deps import CurrentUser, DbSession
from sample_application.backend.errors import AppError
from sample_application.backend.schemas import PasswordChange, ProfileUpdate, UserOut

router = APIRouter(prefix="/profile", tags=["profile"])


@router.get("")
def get_profile(user: CurrentUser) -> UserOut:
    return UserOut.model_validate(user)


@router.put("")
def update_profile(body: ProfileUpdate, db: DbSession, user: CurrentUser) -> UserOut:
    return UserOut.model_validate(repo.update_user(db, user, body.model_dump(), acting=user))


@router.post("/password", status_code=status.HTTP_204_NO_CONTENT)
def change_password(body: PasswordChange, db: DbSession, user: CurrentUser) -> None:
    repo.change_password(db, user, body.current_password, body.new_password)


@router.post("/avatar")
async def upload_avatar(file: UploadFile, db: DbSession, user: CurrentUser) -> UserOut:
    content = await file.read(repo.AVATAR_MAX_BYTES + 1)
    repo.set_avatar(db, user, content, file.content_type)
    return UserOut.model_validate(user)


@router.get("/avatar")
def get_avatar(user: CurrentUser) -> Response:
    if not user.has_avatar or user.avatar is None:
        raise AppError(404, "No avatar uploaded")
    return Response(user.avatar, media_type=user.avatar_content_type)
