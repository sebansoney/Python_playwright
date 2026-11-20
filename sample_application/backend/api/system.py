from fastapi import APIRouter, status

from sample_application.backend.config import config
from sample_application.backend.errors import AppError
from sample_application.backend.seed import init_db

router = APIRouter(tags=["system"])

VERSION = "1.0.0"


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "env": config.env, "version": VERSION}


@router.post("/test-support/reset", status_code=status.HTTP_204_NO_CONTENT)
def reset_database() -> None:
    """Wipe and reseed the database. Exists ONLY when APP_ENV=test."""
    if not config.is_test:
        raise AppError(404, "Not Found")
    init_db(reset=True)
