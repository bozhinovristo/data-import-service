"""CLI entry point: seed the local DB with demo employees and export snapshots.

Run as:  poetry run python -m src.seed_cmd

This populates the configured SQLite database with a small set of realistic demo
records (no external API required), then writes `employees.json` and
`employees.csv` snapshots read back *from the database* — the sample-output
deliverables. Like fetch_cmd, this is an entry point and so configures the root
logger. It must never import src.service.
"""

import csv
import json
import logging
import sqlite3
from typing import Any

from src import database
from src.config import settings
from src.models import Employee

logger = logging.getLogger(__name__)

JSON_PATH = "employees.json"
CSV_PATH = "employees.csv"

# Demo employees mirroring the API's record shape (note `rating` is a string, as
# the real API returns it, so seeding exercises the same coercion path as a live
# fetch). Countries and ratings are deliberately varied so the /employees
# filters (country, min_rating, sort) have something meaningful to show.
DEMO_EMPLOYEES: list[dict[str, Any]] = [
    {
        "id": "8c8c13b6-35ed-3ffb-92d5-c438825df67f",
        "date_of_birth": "1990-06-29",
        "image": "https://example.com/img/1.png",
        "email": "dayni.mayez@example.com",
        "first_name": "Dayni",
        "last_name": "Mayez",
        "title": "Mr.",
        "address": "18342 Alisa Square Suite 259",
        "country": "USA",
        "bio": "Backend engineer who enjoys clean data pipelines.",
        "rating": "3.0600000000000001",
    },
    {
        "id": "1f0a2b3c-4d5e-6f70-8190-a1b2c3d4e5f6",
        "date_of_birth": "1988-02-14",
        "image": "https://example.com/img/2.png",
        "email": "alice.smith@example.com",
        "first_name": "Alice",
        "last_name": "Smith",
        "title": "Ms.",
        "address": "742 Evergreen Terrace",
        "country": "USA",
        "bio": "Staff engineer focused on developer tooling.",
        "rating": "4.7",
    },
    {
        "id": "2a3b4c5d-6e7f-8091-a2b3-c4d5e6f70819",
        "date_of_birth": "1992-11-03",
        "image": "https://example.com/img/3.png",
        "email": "bob.jones@example.com",
        "first_name": "Bob",
        "last_name": "Jones",
        "title": "Mr.",
        "address": "55 King Street West",
        "country": "Canada",
        "bio": "Data analyst with a soft spot for SQLite.",
        "rating": "2.9",
    },
    {
        "id": "3b4c5d6e-7f80-91a2-b3c4-d5e6f7081920",
        "date_of_birth": "1985-07-21",
        "image": "https://example.com/img/4.png",
        "email": "carlos.mendez@example.com",
        "first_name": "Carlos",
        "last_name": "Mendez",
        "title": "Dr.",
        "address": "Rua das Flores 123",
        "country": "Brazil",
        "bio": "Researcher turned platform engineer.",
        "rating": "3.8",
    },
    {
        "id": "4c5d6e7f-8091-a2b3-c4d5-e6f708192031",
        "date_of_birth": "1995-04-09",
        "image": "https://example.com/img/5.png",
        "email": "yuki.tanaka@example.com",
        "first_name": "Yuki",
        "last_name": "Tanaka",
        "title": "Ms.",
        "address": "2-1-1 Nihonbashi",
        "country": "Japan",
        "bio": "Frontend specialist who loves accessibility.",
        "rating": "4.95",
    },
    {
        "id": "5d6e7f80-91a2-b3c4-d5e6-f70819203142",
        "date_of_birth": "1991-09-30",
        "image": "https://example.com/img/6.png",
        "email": "emma.mueller@example.com",
        "first_name": "Emma",
        "last_name": "Müller",
        "title": "Ms.",
        "address": "Hauptstraße 5",
        "country": "Germany",
        "bio": "SRE who keeps the pagers quiet.",
        "rating": "1.6",
    },
    {
        "id": "6e7f8091-a2b3-c4d5-e6f7-081920314253",
        "date_of_birth": "1987-12-12",
        "image": "https://example.com/img/7.png",
        "email": "olivia.brown@example.com",
        "first_name": "Olivia",
        "last_name": "Brown",
        "title": "Mrs.",
        "address": "221B Baker Street",
        "country": "United Kingdom",
        "bio": "QA lead with a test for everything.",
        "rating": "4.2",
    },
    {
        "id": "7f8091a2-b3c4-d5e6-f708-192031425364",
        "date_of_birth": "1993-03-18",
        "image": "https://example.com/img/8.png",
        "email": "raj.patel@example.com",
        "first_name": "Raj",
        "last_name": "Patel",
        "title": "Mr.",
        "address": "12 MG Road",
        "country": "Australia",
        "bio": "Full-stack developer and reluctant DBA.",
        "rating": "3.3",
    },
]


def seed(conn: sqlite3.Connection) -> int:
    """Validate and upsert the demo employees. Returns the number seeded.

    Does not commit — the caller owns the transaction boundary (mirrors the
    contract of database.upsert_employee).
    """
    for raw in DEMO_EMPLOYEES:
        employee = Employee.model_validate(raw)
        database.upsert_employee(conn, employee)
    return len(DEMO_EMPLOYEES)


def export_json(conn: sqlite3.Connection, path: str) -> int:
    """Write all stored employees to `path` as pretty JSON. Returns row count."""
    rows = database.query_employees(conn, limit=1000)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(rows, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    return len(rows)


def export_csv(conn: sqlite3.Connection, path: str) -> int:
    """Write all stored employees to `path` as CSV. Returns row count."""
    rows = database.query_employees(conn, limit=1000)
    fieldnames = list(database._COLUMNS)
    with open(path, "w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return len(rows)


def main() -> None:
    """Seed the configured database with demo data and export JSON/CSV snapshots."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )
    logger.info("Seeding demo data")

    database.init_db(settings.db_path)
    conn = sqlite3.connect(settings.db_path)
    try:
        seeded = seed(conn)
        conn.commit()
        logger.info("Seeded %d demo employees into %s", seeded, settings.db_path)

        json_rows = export_json(conn, JSON_PATH)
        csv_rows = export_csv(conn, CSV_PATH)
        logger.info(
            "Exported %d rows to %s and %d rows to %s",
            json_rows,
            JSON_PATH,
            csv_rows,
            CSV_PATH,
        )
    finally:
        conn.close()


if __name__ == "__main__":
    main()
