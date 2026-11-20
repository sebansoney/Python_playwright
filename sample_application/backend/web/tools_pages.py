"""'Tools' page: the playground for download, upload, iframe, popup and dynamic content."""

import csv
import io
from datetime import UTC, datetime

from fastapi import APIRouter, Request, UploadFile
from fastapi.responses import Response
from pydantic import ValidationError

from sample_application.backend import repository as repo
from sample_application.backend.deps import DbSession
from sample_application.backend.errors import AppError
from sample_application.backend.schemas import ProductCreate
from sample_application.backend.validation import error_list
from sample_application.backend.web.common import WebUser, render

router = APIRouter()

CSV_COLUMNS = ("name", "sku", "category", "price", "stock", "description")
IMPORT_MAX_BYTES = 200_000


@router.get("/tools")
def tools(request: Request, _user: WebUser) -> Response:
    return render(request, "tools.html", {"import_result": None})


@router.get("/tools/export.csv")
def export_csv(db: DbSession, _user: WebUser) -> Response:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(CSV_COLUMNS)
    for p in repo.all_products(db):
        writer.writerow([p.name, p.sku, p.category, f"{p.price:.2f}", p.stock, p.description or ""])
    filename = f"products_{datetime.now(UTC):%Y%m%d}.csv"
    return Response(
        buffer.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/tools/import")
async def import_csv(
    request: Request, db: DbSession, user: WebUser, file: UploadFile | None = None
) -> Response:
    result: dict[str, object] = {"imported": 0, "errors": [], "file_error": None}
    if file is None or not file.filename:
        result["file_error"] = "Choose a CSV file to import"
    elif not file.filename.lower().endswith(".csv"):
        result["file_error"] = "Only .csv files are supported"
    else:
        raw = await file.read(IMPORT_MAX_BYTES + 1)
        if len(raw) > IMPORT_MAX_BYTES:
            result["file_error"] = "File is too large (max 200 KB)"
        else:
            _import_rows(db, user, raw.decode("utf-8-sig", errors="replace"), result)
    status = 400 if result["file_error"] else 200
    return render(request, "tools.html", {"import_result": result}, status_code=status)


def _import_rows(db: DbSession, user: WebUser, text: str, result: dict[str, object]) -> None:
    reader = csv.DictReader(io.StringIO(text))
    missing = [c for c in CSV_COLUMNS[:5] if c not in (reader.fieldnames or [])]
    if missing:
        result["file_error"] = f"Missing required column(s): {', '.join(missing)}"
        return
    errors: list[dict[str, object]] = []
    imported = 0
    for line_no, row in enumerate(reader, start=2):  # line 1 is the header
        data = {k: v.strip() for k, v in row.items() if k in CSV_COLUMNS and v and v.strip()}
        try:
            repo.create_product(db, ProductCreate(**data), creator=user)
            imported += 1
        except ValidationError as exc:
            msgs = [f"{e['field']}: {e['message']}" for e in error_list(exc.errors())]
            errors.append({"line": line_no, "message": "; ".join(msgs)})
        except AppError as exc:
            errors.append({"line": line_no, "message": str(exc.detail)})
    result["imported"] = imported
    result["errors"] = errors


@router.get("/help")
def help_page(request: Request) -> Response:
    """Rendered inside an <iframe> on the Tools page and in a popup window."""
    return render(request, "help.html")
