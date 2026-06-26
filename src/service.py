"""FastAPI layer.

Reads exclusively from the local SQLite database. This module must NEVER import
`src.api_client` — directly or transitively. Allowed imports: src.config,
src.database, src.models, stdlib, and FastAPI.
"""

import csv
import io
import logging
import sqlite3
from collections.abc import AsyncIterator, Generator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Query, Response
from fastapi.responses import JSONResponse, StreamingResponse

from src import database
from src.config import settings

logger = logging.getLogger(__name__)


def _db_path() -> str:
    """Resolve the sqlite3 path from settings.

    The parsing logic now lives on `Settings.db_path` (shared with fetch_cmd).
    This thin wrapper is kept as a seam so tests can monkeypatch the path
    per request without mutating the global settings object.
    """
    return settings.db_path


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    database.init_db(_db_path())
    logger.info("Database initialised")
    yield


app = FastAPI(title="Employee Service", lifespan=lifespan)


def get_conn() -> Generator[sqlite3.Connection, None, None]:
    """Open a fresh SQLite connection per request and close it afterwards."""
    conn = sqlite3.connect(_db_path())
    try:
        yield conn
    finally:
        conn.close()


def _to_csv(rows: list[dict[str, Any]]) -> StreamingResponse:
    """Render employee rows as a streaming CSV download."""
    if not rows:
        fieldnames = list(database._COLUMNS)
    else:
        fieldnames = list(rows[0].keys())

    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(rows)
    buffer.seek(0)

    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=employees.csv"},
    )


@app.get("/employees")
def list_employees(
    country: str | None = None,
    min_rating: float | None = None,
    sort: str | None = None,
    format: str = "json",
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    conn: sqlite3.Connection = Depends(get_conn),
) -> Response:
    logger.debug(
        "list_employees country=%s min_rating=%s sort=%s format=%s limit=%s offset=%s",
        country,
        min_rating,
        sort,
        format,
        limit,
        offset,
    )
    try:
        rows = database.query_employees(conn, country, min_rating, sort, limit, offset)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e

    logger.debug("list_employees returned %d rows", len(rows))

    if format == "csv":
        return _to_csv(rows)
    return JSONResponse(content=rows)


@app.get("/employees/{employee_id}")
def get_employee(
    employee_id: str,
    conn: sqlite3.Connection = Depends(get_conn),
) -> dict[str, Any]:
    row = database.get_employee_by_id(conn, employee_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Employee not found")
    return row
