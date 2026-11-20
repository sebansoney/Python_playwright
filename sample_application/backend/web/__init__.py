"""Server-rendered web pages."""

from fastapi import APIRouter

from sample_application.backend.web import (
    auth_pages,
    dashboard_pages,
    product_pages,
    profile_pages,
    tools_pages,
    user_pages,
)

web_router = APIRouter(include_in_schema=False)
for module in (auth_pages, dashboard_pages, user_pages, product_pages, profile_pages, tools_pages):
    web_router.include_router(module.router)
