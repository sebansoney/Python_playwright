"""REST API (/api/v1)."""

from fastapi import APIRouter

from sample_application.backend.api import auth, notifications, products, profile, system, users

API_PREFIX = "/api/v1"

api_router = APIRouter(prefix=API_PREFIX)
for module in (system, auth, users, products, profile, notifications):
    api_router.include_router(module.router)
