"""CLI entry point: authenticate, fetch employees, validate, and store them.

Run as:  poetry run python -m src.fetch_cmd

This module is the pipeline orchestrator and the ONLY place that configures the
root logger. It must never import src.service.
"""

import logging
import sqlite3

from pydantic import ValidationError

from src import database
from src.api_client import client as api_client
from src.config import settings
from src.models import Employee

logger = logging.getLogger(__name__)


def main() -> None:
    """Run the full fetch → validate → store pipeline."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )
    logger.info("Starting employee import")

    conn = sqlite3.connect(settings.db_path)
    try:
        database.init_db(settings.db_path)
        logger.info("Database ready at %s", settings.db_path)

        raw_records = api_client.fetch_employees()
        logger.info("Fetched %d raw records from API", len(raw_records))

        stored = 0
        skipped = 0
        for raw in raw_records:
            try:
                employee = Employee.model_validate(raw)
                database.upsert_employee(conn, employee)
                stored += 1
            except ValidationError as exc:
                logger.warning(
                    "Skipping malformed record id=%s: %s",
                    raw.get("id", "<unknown>"),
                    exc,
                )
                skipped += 1

        conn.commit()

        logger.info(
            "Import complete: %d stored, %d skipped (total fetched: %d)",
            stored,
            skipped,
            len(raw_records),
        )
    finally:
        conn.close()


if __name__ == "__main__":
    main()
