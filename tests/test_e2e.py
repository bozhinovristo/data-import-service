from pathlib import Path

import httpx
import pytest
import respx
from fastapi.testclient import TestClient

from src import database, service
from src.config import settings
from src.fetch_cmd import main as fetch_main
from src.service import app

AUTH_RESPONSE = {
    "access_token": "test-token-abc123",
    "token_type": "bearer",
    "expires_at": "2099-01-01T00:00:00+00:00",
}

EMPLOYEE_1 = {
    "id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
    "date_of_birth": "1990-06-15",
    "image": "https://example.com/img1.png",
    "email": "alice@example.com",
    "first_name": "Alice",
    "last_name": "Smith",
    "title": "Ms.",
    "address": "1 Main St",
    "country": "USA",
    "bio": "Bio for Alice.",
    "rating": "4.5",
}

EMPLOYEE_2 = {
    "id": "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
    "date_of_birth": "1985-03-22",
    "image": "https://example.com/img2.png",
    "email": "bob@example.com",
    "first_name": "Bob",
    "last_name": "Jones",
    "title": "Mr.",
    "address": "2 Oak Ave",
    "country": "Canada",
    "bio": "Bio for Bob.",
    "rating": "3.2",
}

EMPLOYEES_RESPONSE = [EMPLOYEE_1, EMPLOYEE_2]


@pytest.fixture
def db_path(tmp_path: Path) -> str:
    path = str(tmp_path / "e2e_test.db")
    database.init_db(path)
    return path


@pytest.fixture
def http_mock():  # type: ignore[no-untyped-def]
    """Mock all httpx calls: auth endpoint + employee list endpoint."""
    base = settings.api_base_url
    with respx.mock(assert_all_called=False) as mock:
        mock.post(f"{base}/api/token/").mock(
            return_value=httpx.Response(200, json=AUTH_RESPONSE)
        )
        mock.get(f"{base}/api/employee/list/").mock(
            return_value=httpx.Response(200, json=EMPLOYEES_RESPONSE)
        )
        yield mock


@pytest.fixture
def e2e_client(db_path: str, http_mock, monkeypatch: pytest.MonkeyPatch):  # type: ignore[no-untyped-def]
    """Run the full fetch pipeline, then return a TestClient over the service."""
    # Point service and fetch_cmd at the test DB.
    monkeypatch.setattr(service, "_db_path", lambda: db_path)
    monkeypatch.setattr("src.fetch_cmd.settings", type("S", (), {"db_path": db_path})())

    # Reset the APIClient token cache so each test authenticates fresh.
    from src.api_client import client as api_client

    api_client._token = None
    api_client._expires_at = None

    # Run the pipeline.
    fetch_main()

    # Return a test client wired to the same DB.
    with TestClient(app) as tc:
        yield tc


def test_happy_path_stores_all_employees(e2e_client: TestClient) -> None:
    resp = e2e_client.get("/employees")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 2
    ids = {e["id"] for e in body}
    assert EMPLOYEE_1["id"] in ids
    assert EMPLOYEE_2["id"] in ids


def test_rating_coerced_to_float(e2e_client: TestClient) -> None:
    resp = e2e_client.get("/employees")
    assert resp.status_code == 200
    for emp in resp.json():
        assert isinstance(emp["rating"], float)


def test_filter_by_country_after_fetch(e2e_client: TestClient) -> None:
    resp = e2e_client.get("/employees", params={"country": "USA"})
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["email"] == "alice@example.com"


def test_get_by_id_after_fetch(e2e_client: TestClient) -> None:
    resp = e2e_client.get(f"/employees/{EMPLOYEE_1['id']}")
    assert resp.status_code == 200
    assert resp.json()["first_name"] == "Alice"


def test_idempotent_fetch_no_duplicates(
    e2e_client: TestClient,
    http_mock,  # type: ignore[no-untyped-def]
    monkeypatch: pytest.MonkeyPatch,
    db_path: str,
) -> None:
    # Reset token so second fetch re-authenticates cleanly.
    from src.api_client import client as api_client

    api_client._token = None
    api_client._expires_at = None

    monkeypatch.setattr("src.fetch_cmd.settings", type("S", (), {"db_path": db_path})())
    # Second fetch run.
    fetch_main()

    resp = e2e_client.get("/employees")
    assert resp.status_code == 200
    assert len(resp.json()) == 2  # still 2, not 4
