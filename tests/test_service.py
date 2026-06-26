import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src import database, service
from src.models import Employee
from src.service import app

BASE: dict = {
    "id": "11111111-1111-1111-1111-111111111111",
    "date_of_birth": "1990-01-01",
    "image": "https://example.com/img.png",
    "email": "test@example.com",
    "first_name": "Test",
    "last_name": "User",
    "title": "Mr.",
    "address": "123 Main St",
    "country": "USA",
    "bio": "Bio text.",
    "rating": "3.5",
}


def insert(db_path: str, **overrides: object) -> None:
    emp = Employee.model_validate({**BASE, **overrides})
    conn = sqlite3.connect(db_path)
    database.upsert_employee(conn, emp)
    conn.commit()
    conn.close()


@pytest.fixture
def db_path(tmp_path: Path) -> str:
    path = str(tmp_path / "test.db")
    database.init_db(path)
    return path


@pytest.fixture
def client(db_path: str, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setattr(service, "_db_path", lambda: db_path)
    with TestClient(app) as test_client:
        yield test_client


def test_list_employees_empty(client: TestClient) -> None:
    resp = client.get("/employees")
    assert resp.status_code == 200
    assert resp.json() == []


def test_list_employees_returns_inserted(client: TestClient, db_path: str) -> None:
    insert(db_path)
    resp = client.get("/employees")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["id"] == BASE["id"]
    assert body[0]["first_name"] == "Test"
    assert body[0]["rating"] == 3.5


def test_filter_by_country(client: TestClient, db_path: str) -> None:
    insert(db_path, id="11111111-1111-1111-1111-111111111111", country="USA")
    insert(db_path, id="22222222-2222-2222-2222-222222222222", country="Canada")

    resp = client.get("/employees", params={"country": "USA"})
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["country"] == "USA"


def test_filter_by_min_rating(client: TestClient, db_path: str) -> None:
    insert(db_path, id="11111111-1111-1111-1111-111111111111", rating="2.0")
    insert(db_path, id="22222222-2222-2222-2222-222222222222", rating="4.5")

    resp = client.get("/employees", params={"min_rating": 3.0})
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["rating"] == 4.5


def test_invalid_sort_returns_422(client: TestClient) -> None:
    resp = client.get("/employees", params={"sort": "id; DROP TABLE employees"})
    assert resp.status_code == 422


def test_csv_format(client: TestClient, db_path: str) -> None:
    insert(db_path)
    resp = client.get("/employees", params={"format": "csv"})
    assert resp.status_code == 200
    assert "text/csv" in resp.headers["content-type"]
    assert "attachment; filename=employees.csv" in resp.headers["content-disposition"]
    first_line = resp.text.splitlines()[0]
    assert first_line.startswith("id,date_of_birth,")


def test_get_employee_by_id(client: TestClient, db_path: str) -> None:
    insert(db_path)
    resp = client.get(f"/employees/{BASE['id']}")
    assert resp.status_code == 200
    assert resp.json()["id"] == BASE["id"]


def test_get_employee_by_id_not_found(client: TestClient) -> None:
    resp = client.get("/employees/does-not-exist")
    assert resp.status_code == 404
