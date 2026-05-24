import csv as csv_lib
import io

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse

from backend.db.client import store
from backend.middleware.auth import require_bearer
from backend.schemas.models import ImportResult
from backend.services.csv_import import run_import, UserAdapter, PostAdapter

router = APIRouter(prefix="/import", tags=["import"])

MAX_FILE_BYTES = 1_048_576  # 1 MB
MAX_ROWS = 1000

_ADAPTERS = {"users": UserAdapter, "posts": PostAdapter}


@router.post(
    "/{resource}",
    response_model=ImportResult,
    dependencies=[Depends(require_bearer)],
)
async def import_csv(
    resource: str,
    file: UploadFile = File(...),
    mode: str = Form("atomic"),
) -> ImportResult:
    if resource not in _ADAPTERS:
        raise HTTPException(status_code=404, detail="unknown resource")

    if mode not in ("atomic", "partial"):
        raise HTTPException(status_code=400, detail="mode must be atomic or partial")

    raw = await file.read()
    if len(raw) > MAX_FILE_BYTES:
        raise HTTPException(status_code=413, detail="file exceeds 1 MB limit")

    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="csv must be utf-8")

    reader = csv_lib.DictReader(io.StringIO(text))
    if reader.fieldnames is None:
        raise HTTPException(status_code=400, detail="empty csv")

    required = _ADAPTERS[resource].required_columns
    missing = [c for c in required if c not in reader.fieldnames]
    if missing:
        raise HTTPException(
            status_code=400, detail=f"missing column {missing[0]}"
        )

    rows = list(reader)
    if len(rows) == 0:
        raise HTTPException(status_code=400, detail="empty csv")
    if len(rows) > MAX_ROWS:
        raise HTTPException(
            status_code=413, detail=f"file exceeds {MAX_ROWS} row limit"
        )

    result = run_import(resource, rows, mode, store)

    if result.rolled_back:
        return JSONResponse(
            status_code=422,
            content=result.model_dump(),
        )
    return result
