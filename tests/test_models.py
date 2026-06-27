import logging

import pytest
from pydantic import ValidationError

from src.models import Employee

VALID_PAYLOAD: dict = {
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
    "rating": "3.0600000000000001",
}


def test_valid_employee_parses_correctly() -> None:
    emp = Employee.model_validate(VALID_PAYLOAD)
    assert str(emp.id) == "12345678-1234-5678-1234-567812345678"
    assert emp.first_name == "Alice"
    assert emp.country == "USA"
    assert emp.fetched_at is None


def test_rating_string_coerces_to_float() -> None:
    emp = Employee.model_validate(VALID_PAYLOAD)
    assert isinstance(emp.rating, float)
    assert abs(emp.rating - 3.06) < 1e-9


def test_rating_already_float_is_accepted() -> None:
    payload = {**VALID_PAYLOAD, "rating": 4.5}
    emp = Employee.model_validate(payload)
    assert emp.rating == 4.5


def test_invalid_email_raises_validation_error() -> None:
    payload = {**VALID_PAYLOAD, "email": "not-an-email"}
    with pytest.raises(ValidationError):
        Employee.model_validate(payload)


def test_unknown_fields_are_ignored() -> None:
    payload = {**VALID_PAYLOAD, "unexpected_field": "should be dropped"}
    emp = Employee.model_validate(payload)
    assert not hasattr(emp, "unexpected_field")


def test_unknown_fields_are_logged(caplog: pytest.LogCaptureFixture) -> None:
    payload = {**VALID_PAYLOAD, "department": "Engineering", "salary": 99000}
    with caplog.at_level(logging.WARNING, logger="src.models"):
        Employee.model_validate(payload)
    # Both unknown fields are named in the warning so they stay traceable.
    assert "department" in caplog.text
    assert "salary" in caplog.text
    assert VALID_PAYLOAD["id"] in caplog.text


def test_missing_required_field_raises_validation_error() -> None:
    payload = {k: v for k, v in VALID_PAYLOAD.items() if k != "first_name"}
    with pytest.raises(ValidationError):
        Employee.model_validate(payload)


def test_date_of_birth_parsed_as_date() -> None:
    from datetime import date

    emp = Employee.model_validate(VALID_PAYLOAD)
    assert emp.date_of_birth == date(1990, 6, 15)
