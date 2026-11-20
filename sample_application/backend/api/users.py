from typing import Annotated

from fastapi import APIRouter, Query, Response, status

from sample_application.backend import repository as repo
from sample_application.backend.deps import AdminUser, CurrentUser, DbSession
from sample_application.backend.errors import AppError
from sample_application.backend.schemas import (
    Page,
    Role,
    UserCreate,
    UserOut,
    UserPatch,
    UserUpdate,
)

router = APIRouter(prefix="/users", tags=["users"])


@router.get("")
def list_users(
    db: DbSession,
    _admin: AdminUser,
    q: Annotated[str | None, Query(max_length=100)] = None,
    role: Role | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> Page[UserOut]:
    rows, total = repo.list_users(db, q, role, page, size)
    return Page[UserOut](
        items=[UserOut.model_validate(u) for u in rows], total=total, page=page, size=size
    )


@router.post("", status_code=status.HTTP_201_CREATED)
def create_user(body: UserCreate, db: DbSession, _admin: AdminUser, response: Response) -> UserOut:
    user = repo.create_user(db, body)
    response.headers["Location"] = f"/api/v1/users/{user.id}"
    return UserOut.model_validate(user)


@router.get("/{user_id}")
def get_user(user_id: int, db: DbSession, current: CurrentUser) -> UserOut:
    if current.role != "admin" and current.id != user_id:
        raise AppError(403, "You can only view your own account")
    return UserOut.model_validate(repo.get_user(db, user_id))


@router.put("/{user_id}")
def replace_user(user_id: int, body: UserUpdate, db: DbSession, admin: AdminUser) -> UserOut:
    user = repo.get_user(db, user_id)
    return UserOut.model_validate(repo.update_user(db, user, body.model_dump(), acting=admin))


@router.patch("/{user_id}")
def patch_user(user_id: int, body: UserPatch, db: DbSession, admin: AdminUser) -> UserOut:
    changes = body.model_dump(exclude_unset=True)
    if not changes:
        raise AppError(400, "No fields to update", code="empty_patch")
    user = repo.get_user(db, user_id)
    return UserOut.model_validate(repo.update_user(db, user, changes, acting=admin))


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(user_id: int, db: DbSession, admin: AdminUser) -> None:
    repo.delete_user(db, repo.get_user(db, user_id), acting=admin)
