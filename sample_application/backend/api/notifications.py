"""Deliberately slow endpoint used by the UI's dynamic-content demo."""

import asyncio
import uuid
from typing import Annotated

from fastapi import APIRouter, Query

from sample_application.backend.deps import CurrentUser
from sample_application.backend.schemas import Notification

router = APIRouter(prefix="/notifications", tags=["notifications"])

_MESSAGES = [
    ("info", "Weekly inventory report is available"),
    ("warning", "5 products are running low on stock"),
    ("success", "Nightly backup completed"),
]


@router.get("")
async def list_notifications(
    _user: CurrentUser, delay_ms: Annotated[int, Query(ge=0, le=5000)] = 0
) -> list[Notification]:
    await asyncio.sleep(delay_ms / 1000)
    # Random ids on purpose: tests must not rely on them (stable-locator lesson).
    return [Notification(id=uuid.uuid4().hex[:8], level=lvl, message=msg) for lvl, msg in _MESSAGES]
