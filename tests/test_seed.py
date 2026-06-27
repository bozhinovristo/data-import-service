import csv
import json
import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest

from src import database, seed_cmd
from src.models import Employee


@pytest.fixture
def conn() -> Iterator[sqlite3.Connection]:
    """Fresh in-memory DB with the employees schema, torn down after each test."""
    connection = sqlite3.connect(":memory:")
    connection.execute(database._CREATE_TABLE_SQL)
    connection.commit()
    yield connection
    connection.close()


def test_demo_data_all_valid() -> None:
    """Every demo record must validate — a typo'd snapshot should fail loudly."""
    for raw in seed_cmd.DEMO_EMPLOYEES:
        Employee.model_validate(raw)


def test_seed_inserts_all_employees(conn: sqlite3.Connection) -> None:
    count = seed_cmd.seed(conn)
    conn.commit()

    assert count == len(seed_cmd.DEMO_EMPLOYEES)
    stored = conn.execute("SELECT COUNT(*) FROM employees").fetchone()[0]
    assert stored == count
    # The spec's sample employee id is included in the demo set.
    row = database.get_employee_by_id(conn, "8c8c13b6-35ed-3ffb-92d5-c438825df67f")
    assert row is not None
    assert row["first_name"] == "Dayni"


def test_seed_is_idempotent(conn: sqlite3.Connection) -> None:
    seed_cmd.seed(conn)
    seed_cmd.seed(conn)
    conn.commit()

    stored = conn.execute("SELECT COUNT(*) FROM employees").fetchone()[0]
    assert stored == len(seed_cmd.DEMO_EMPLOYEES)  # upsert, not duplicate


def test_export_json_roundtrips_from_db(
    conn: sqlite3.Connection, tmp_path: Path
) -> None:
    seed_cmd.seed(conn)
    conn.commit()
    out = tmp_path / "employees.json"

    written = seed_cmd.export_json(conn, str(out))

    data = json.loads(out.read_text(encoding="utf-8"))
    assert written == len(data) == len(seed_cmd.DEMO_EMPLOYEES)
    for emp in data:
        assert isinstance(emp["rating"], float)  # normalized, not the source string
        assert emp["fetched_at"]  # stamped by the DB layer
    assert set(data[0].keys()) == set(database._COLUMNS)


def test_export_csv_roundtrips_from_db(
    conn: sqlite3.Connection, tmp_path: Path
) -> None:
    seed_cmd.seed(conn)
    conn.commit()
    out = tmp_path / "employees.csv"

    written = seed_cmd.export_csv(conn, str(out))

    text = out.read_text(encoding="utf-8")
    lines = text.splitlines()
    assert lines[0] == ",".join(database._COLUMNS)
    assert written == len(seed_cmd.DEMO_EMPLOYEES)

    rows = list(csv.DictReader(text.splitlines()))
    assert len(rows) == written
    assert {r["country"] for r in rows} >= {"USA", "Canada", "Japan"}
