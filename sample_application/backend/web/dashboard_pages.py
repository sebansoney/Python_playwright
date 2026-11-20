from fastapi import APIRouter, Request
from fastapi.responses import Response

from sample_application.backend import repository as repo
from sample_application.backend.deps import DbSession
from sample_application.backend.web.common import WebUser, render

router = APIRouter()


@router.get("/dashboard")
def dashboard(request: Request, db: DbSession, _user: WebUser) -> Response:
    return render(request, "dashboard.html", {"stats": repo.dashboard_stats(db)})
