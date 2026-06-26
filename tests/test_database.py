import sqlite3
from collections.abc import Iterator

import pytest

from src import database
from src.models import Employee

BASE_PAYLOAD: dict = {
    "id": "12345678-1234-5678-1234-567812345678",
    "date_of_birth": "1990-06-15",
    "image": "https://example.com/avatar.png",
    "email": "alice@example.com",
    "first_name": "Alice",
    "last_name": "Smith",
    "title": "Engineer",
    "address": "123 Main St",
    "country": "USA",
    "bio": "Some bio.",
    "rating": "4.5",
}


def make_employee(**overrides: object) -> Employee:
    """Build a valid Employee, overriding any fields for the test at hand."""
    return Employee.model_validate({**BASE_PAYLOAD, **overrides})


@pytest.fixture
def conn() -> Iterator[sqlite3.Connection]:
    """Fresh in-memory DB with the employees schema, torn down after each test."""
    connection = sqlite3.connect(":memory:")
    connection.execute(database._CREATE_TABLE_SQL)
    connection.commit()
    yield connection
    connection.close()


def test_upsert_inserts_new_employee(conn: sqlite3.Connection) -> None:
    database.upsert_employee(conn, make_employee())

    row = database.get_employee_by_id(conn, BASE_PAYLOAD["id"])
    assert row is not None
    assert row["first_name"] == "Alice"
    assert row["country"] == "USA"
    assert row["rating"] == 4.5
    # fetched_at is always populated by the DB layer.
    assert row["fetched_at"]


def test_upsert_same_id_updates_not_duplicates(conn: sqlite3.Connection) -> None:
    database.upsert_employee(conn, make_employee(country="USA"))
    database.upsert_employee(conn, make_employee(country="Canada"))

    count = conn.execute("SELECT COUNT(*) FROM employees").fetchone()[0]
    assert count == 1

    row = database.get_employee_by_id(conn, BASE_PAYLOAD["id"])
    assert row is not None
    assert row["country"] == "Canada"


def test_query_by_country_filters(conn: sqlite3.Connection) -> None:
    database.upsert_employee(
        conn, make_employee(id="11111111-1111-1111-1111-111111111111", country="USA")
    )
    database.upsert_employee(
        conn,
        make_employee(id="22222222-2222-2222-2222-222222222222", country="Canada"),
    )

    usa = database.query_employees(conn, country="USA")
    assert len(usa) == 1
    assert usa[0]["country"] == "USA"


def test_query_by_min_rating_filters(conn: sqlite3.Connection) -> None:
    database.upsert_employee(
        conn, make_employee(id="11111111-1111-1111-1111-111111111111", rating="2.0")
    )
    database.upsert_employee(
        conn, make_employee(id="22222222-2222-2222-2222-222222222222", rating="4.0")
    )

    high = database.query_employees(conn, min_rating=3.5)
    assert len(high) == 1
    assert high[0]["rating"] == 4.0

    # Inclusive boundary: exactly 4.0 is returned for min_rating=4.0.
    inclusive = database.query_employees(conn, min_rating=4.0)
    assert len(inclusive) == 1


def test_invalid_sort_raises_value_error(conn: sqlite3.Connection) -> None:
    with pytest.raises(ValueError):
        database.query_employees(conn, sort="id; DROP TABLE employees")


def test_get_employee_by_id_returns_employee(conn: sqlite3.Connection) -> None:
    database.upsert_employee(conn, make_employee())

    row = database.get_employee_by_id(conn, BASE_PAYLOAD["id"])
    assert row is not None
    assert row["id"] == BASE_PAYLOAD["id"]
    assert row["email"] == "alice@example.com"


def test_get_employee_by_id_unknown_returns_none(conn: sqlite3.Connection) -> None:
    result = database.get_employee_by_id(conn, "00000000-0000-0000-0000-000000000000")
    assert result is None
