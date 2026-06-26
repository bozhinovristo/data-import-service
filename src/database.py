"""SQLite persistence layer (stdlib sqlite3 only)

Owns the employees schema, upserts validated `Employee` models, and serves
filtered/paginated queries back to the FastAPI layer.
"""

import logging
import sqlite3
from datetime import datetime, timezone
from typing import Any

from src.models import Employee

logger = logging.getLogger(__name__)

# Whitelist of sortable columns. ORDER BY cannot be parameterized, so the sort
# value is interpolated into SQL — it MUST be validated against this set first
# to prevent SQL injection.
ALLOWED_SORT_FIELDS = {"first_name", "last_name", "rating", "date_of_birth"}

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS employees (
    id TEXT PRIMARY KEY,
    date_of_birth TEXT,
    image TEXT,
    email TEXT,
    first_name TEXT,
    last_name TEXT,
    title TEXT,
    address TEXT,
    country TEXT,
    bio TEXT,
    rating REAL,
    fetched_at TEXT NOT NULL
)
"""

_COLUMNS = (
    "id",
    "date_of_birth",
    "image",
    "email",
    "first_name",
    "last_name",
    "title",
    "address",
    "country",
    "bio",
    "rating",
    "fetched_at",
)


def init_db(db_path: str) -> None:
    """Create the employees table if it doesn't already exist."""
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(_CREATE_TABLE_SQL)
        conn.commit()
        logger.info("Initialized database at %s", db_path)
    finally:
        conn.close()


def upsert_employee(conn: sqlite3.Connection, employee: Employee) -> None:
    """Insert or replace an employee by id, stamping a fresh fetched_at.

    Does not commit — the caller owns the transaction boundary, so a batch of
    upserts can be committed as a single transaction.
    """
    data = employee.model_dump(mode="json")
    data["fetched_at"] = datetime.now(timezone.utc).isoformat()
    placeholders = ", ".join(f":{col}" for col in _COLUMNS)
    columns = ", ".join(_COLUMNS)
    conn.execute(
        f"INSERT OR REPLACE INTO employees ({columns}) VALUES ({placeholders})",
        data,
    )
    logger.debug("Upserted employee id=%s", data["id"])


def query_employees(
    conn: sqlite3.Connection,
    country: str | None = None,
    min_rating: float | None = None,
    sort: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """Return employees matching the given filters, sorted and paginated.

    `sort`, when provided, must be one of ALLOWED_SORT_FIELDS; any other value
    raises ValueError (SQL-injection guard, since ORDER BY can't be bound).
    """
    if sort is not None and sort not in ALLOWED_SORT_FIELDS:
        raise ValueError(f"Invalid sort field: {sort!r}")

    clauses: list[str] = []
    params: dict[str, Any] = {}
    if country is not None:
        clauses.append("country = :country")
        params["country"] = country
    if min_rating is not None:
        clauses.append("rating >= :min_rating")
        params["min_rating"] = min_rating

    sql = "SELECT * FROM employees"
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    if sort is not None:
        sql += f" ORDER BY {sort}"  # safe: validated against allowlist above
    sql += " LIMIT :limit OFFSET :offset"
    params["limit"] = limit
    params["offset"] = offset

    conn.row_factory = sqlite3.Row
    rows = conn.execute(sql, params).fetchall()
    return [dict(row) for row in rows]


def get_employee_by_id(
    conn: sqlite3.Connection, employee_id: str
) -> dict[str, Any] | None:
    """Return a single employee dict by id, or None if not found."""
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT * FROM employees WHERE id = :id", {"id": employee_id}
    ).fetchone()
    return dict(row) if row is not None else None
