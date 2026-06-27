"""Resilience tests for the fetch pipeline (fetch_cmd.main).

Covers the spec's "gracefully handle empty lists / malformed records (log &
skip)" requirement, plus that unknown fields don't abort a fetch. HTTP is mocked
with respx; each test runs against a fresh temp-file SQLite DB.
"""

import logging
import sqlite3
from pathlib import Path

import httpx
import pytest
import respx

from src import database, fetch_cmd
from src.api_client import client as api_client
from src.config import settings

AUTH_RESPONSE = {
    "access_token": "test-token",
    "token_type": "bearer",
    "expires_at": "2099-01-01T00:00:00+00:00",
}

VALID_EMPLOYEE = {
    "id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
    "date_of_birth": "1990-06-15",
    "image": "https://example.com/img.png",
    "email": "valid@example.com",
    "first_name": "Valid",
    "last_name": "Person",
    "title": "Ms.",
    "address": "1 Main St",
    "country": "USA",
    "bio": "A valid record.",
    "rating": "4.1",
}

# Same shape as VALID_EMPLOYEE but with an invalid email, so model validation
# fails and fetch_cmd must skip it rather than abort the whole batch.
MALFORMED_EMPLOYEE = {
    **VALID_EMPLOYEE,
    "id": "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
    "email": "not-a-valid-email",
}


@pytest.fixture
def db_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    """Temp-file DB wired into fetch_cmd, with the client token cache reset."""
    path = str(tmp_path / "fetch.db")
    database.init_db(path)
    monkeypatch.setattr(fetch_cmd, "settings", type("S", (), {"db_path": path})())
    api_client._token = None
    api_client._expires_at = None
    return path


def _mock_employee_list(employees: list[dict]) -> None:
    """Register auth + employee-list mock routes returning `employees`."""
    base = settings.api_base_url
    respx.post(f"{base}/api/token/").mock(
        return_value=httpx.Response(200, json=AUTH_RESPONSE)
    )
    respx.get(f"{base}/api/employee/list/").mock(
        return_value=httpx.Response(200, json=employees)
    )


def _stored_ids(db_path: str) -> list[str]:
    conn = sqlite3.connect(db_path)
    try:
        return [row[0] for row in conn.execute("SELECT id FROM employees")]
    finally:
        conn.close()


@respx.mock
def test_malformed_record_skipped_others_stored(
    db_path: str, caplog: pytest.LogCaptureFixture
) -> None:
    _mock_employee_list([VALID_EMPLOYEE, MALFORMED_EMPLOYEE])

    with caplog.at_level(logging.WARNING):
        fetch_cmd.main()

    ids = _stored_ids(db_path)
    assert ids == [VALID_EMPLOYEE["id"]]  # valid stored, malformed skipped
    # The skip is logged with the offending record's id for traceability.
    assert MALFORMED_EMPLOYEE["id"] in caplog.text


@respx.mock
def test_empty_list_handled_gracefully(db_path: str) -> None:
    _mock_employee_list([])

    fetch_cmd.main()  # must not raise

    assert _stored_ids(db_path) == []


@respx.mock
def test_unknown_fields_do_not_crash_fetch(
    db_path: str, caplog: pytest.LogCaptureFixture
) -> None:
    record_with_extra = {**VALID_EMPLOYEE, "department": "Engineering"}
    _mock_employee_list([record_with_extra])

    with caplog.at_level(logging.WARNING):
        fetch_cmd.main()

    assert _stored_ids(db_path) == [VALID_EMPLOYEE["id"]]  # stored despite extra
    assert "department" in caplog.text  # and the unknown field was logged
