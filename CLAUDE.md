# CLAUDE.md — Data Import Service (alternativly: Employee Importer Project)

This file is the single source of truth for how Claude Code should operate in this codebase.
Read it fully before writing any code.

---

## Project Overview

A Python application that:
1. Authenticates against an external API and fetches employee records.
2. Validates, normalizes, and persists them to a local SQLite database.
3. Exposes stored employees through a FastAPI HTTP service.

**The FastAPI service never calls the external API.** It reads only from local storage.

---

## Commands

```bash
# Install dependencies
poetry install

# Fetch employees from external API and store to DB
poetry run python -m src.fetch_cmd

# Run the FastAPI service (dev)
poetry run uvicorn src.service:app --reload --port 8000

# Run all tests
poetry run pytest

# Run tests with coverage
poetry run pytest --cov=src --cov-report=term-missing

# Lint
poetry run ruff check .

# Format
poetry run black .

# Type check
poetry run mypy src/

# Run lint + format + typecheck together (do before every commit)
poetry run ruff check . && poetry run black . && poetry run mypy src/
```

---

## Architecture

```
External API
    │
    ▼
api_client.py       ← authenticate, token cache, fetch, retries
    │
    ▼
models.py           ← Pydantic v2 Employee model, validation, normalization
    │
    ▼
database.py         ← SQLite upsert, query, fetched_at timestamp
    │
    ▼
service.py          ← FastAPI: GET /employees, GET /employees/{id}
```

**config.py** sits across all layers — it loads `.env` via `pydantic-settings` and is
the only place environment variables are read.

---

## File Responsibilities

| File | Responsibility |
|---|---|
| `src/config.py` | Load and validate all env vars via pydantic-settings. |
| `src/models.py` | Pydantic v2 Employee model + DB row dataclass. |
| `src/api_client.py` | Auth, token caching, employee fetch, retries. |
| `src/database.py` | SQLite init, upsert employees, query with filters. |
| `src/service.py` | FastAPI app, route handlers, CSV/JSON response. |
| `src/fetch_cmd.py` | CLI entry point: auth → fetch → store. |
| `tests/test_models.py` | Validation edge cases, type coercion, unknown fields. |
| `tests/test_api_client.py` | Mocked httpx: auth success, 401, 500 retry. |
| `tests/test_e2e.py` | Full happy path: mock API → fetch → store → GET /employees. |

---

## Critical Implementation Rules

### 1. Auth Header Abstraction

The external API uses `Access-Token` (non-standard). Never hardcode this string across
multiple files. Abstract it in `api_client.py`:

```python
# api_client.py
AUTH_HEADER_NAME = "Access-Token"  # single place to change if spec changes

def _auth_headers(token: str) -> dict[str, str]:
    return {AUTH_HEADER_NAME: token}
```

Switching to `Authorization: Bearer {token}` must be a one-line change.

### 2. Token Expiry

Always check token validity before making API calls. Never assume a cached token is still live.

```python
from datetime import datetime, timezone

def _is_token_valid(expires_at: str) -> bool:
    return datetime.fromisoformat(expires_at) > datetime.now(timezone.utc)
```

Re-authenticate automatically when the token is expired or missing.

### 3. Rating Field Coercion

The API returns `rating` as a string (e.g., `"3.0600000000000001"`). The Pydantic model
must coerce it to `float`. Use a `@field_validator` with `mode='before'`:

```python
@field_validator("rating", mode="before")
@classmethod
def parse_rating(cls, v: str | float) -> float:
    return float(v)
```

### 4. Pydantic v2 Only

This project uses **Pydantic v2**. Never use v1 patterns:

| v1 (forbidden) | v2 (correct) |
|---|---|
| `class Config:` | `model_config = ConfigDict(...)` |
| `@validator` | `@field_validator` |
| `.dict()` | `.model_dump()` |
| `parse_obj()` | `model_validate()` |

### 5. Unknown Fields — Log and Tolerate

The Employee model must not crash on unknown fields from the API. Configure:

```python
model_config = ConfigDict(extra="ignore")
```

Log a warning when unknown fields are encountered during fetch so they are traceable.

### 6. Malformed Records — Log and Skip

In `fetch_cmd.py`, wrap each record's validation in try/except. Log the error and the
record's raw `id` (if available), then continue to the next record:

```python
for raw in raw_employees:
    try:
        employee = Employee.model_validate(raw)
        db.upsert(employee)
    except ValidationError as e:
        logger.warning("Skipping malformed record id=%s: %s", raw.get("id"), e)
```

### 7. Secrets — Never in Source Code

- `.env` is in `.gitignore` from the first commit.
- `.env.example` is committed with empty values.
- All config is loaded exclusively through `config.py` using `pydantic-settings`.
- No `os.getenv()` calls scattered across files — route everything through `Settings`.

### 8. Database Upsert

Use `INSERT OR REPLACE` (SQLite) keyed on `id` (UUID). Repeated fetches must not
duplicate rows. Always write `fetched_at = datetime.now(timezone.utc).isoformat()`.

### 9. FastAPI Service — Reads DB Only

`service.py` imports `database.py` functions directly. It never imports `api_client.py`.
This is enforced by architecture — if you find yourself importing the API client from
the service layer, stop and reconsider.

---

## /employees Endpoint Spec

```
GET /employees
  ?country=USA           — exact match, case-sensitive
  ?min_rating=3.5        — float, inclusive
  ?sort=rating           — one of: first_name, last_name, rating, date_of_birth
  ?format=csv            — default: json; csv returns text/csv with StreamingResponse
  ?limit=20              — pagination (nice-to-have)
  ?offset=0              — pagination (nice-to-have)

GET /employees/{id}      — nice-to-have, returns single employee or 404
```

CSV export must use `io.StringIO` + `csv.DictWriter` and return a `StreamingResponse`
with `media_type="text/csv"` and a `Content-Disposition` header.

---

## Retry Policy

Use `tenacity` for HTTP retries in `api_client.py`:

```python
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

@retry(
    retry=retry_if_exception_type(httpx.HTTPStatusError),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
)
def fetch_employees(token: str) -> list[dict]: ...
```

Retry only on 5xx errors and network-level exceptions — not on 4xx (those are caller errors).

---

## Logging

Use stdlib `logging` throughout. Never use `print()` in production code.

```python
import logging
logger = logging.getLogger(__name__)
```

Configure the root logger in `fetch_cmd.py` and `service.py` entry points only.
Log levels: `DEBUG` for HTTP request details, `INFO` for milestones, `WARNING` for
skipped/malformed records, `ERROR` for unrecoverable failures.

---

## Testing Conventions

- All tests live in `tests/`.
- Use `pytest` fixtures for DB setup/teardown — each test gets a fresh in-memory SQLite DB.
- Mock HTTP at the `httpx` transport level using `httpx.MockTransport` or `respx`.
- Tests must not make real network calls.
- The e2e test (`test_e2e.py`) runs the full pipeline end-to-end with mocked HTTP and
  an in-memory DB, then calls the FastAPI test client to assert the response.

```python
# Example e2e fixture pattern
from fastapi.testclient import TestClient
from src.service import app

client = TestClient(app)

def test_happy_path():
    # 1. Mock API auth + employee list responses
    # 2. Run fetch_cmd logic with test DB
    # 3. Assert GET /employees returns expected employees
```

---

## Environment Variables

Defined in `.env.example`:

```
API_BASE_URL=http://localhost
API_CLIENT_ID=
API_CLIENT_SECRET=
API_USERNAME=
API_PASSWORD=
DATABASE_URL=sqlite:///./employees.db
```

All variables are required. `pydantic-settings` will raise at startup if any are missing.

---

## Code Style

- Python 3.11+.
- Type annotations on every function signature — no bare `Any` unless truly unavoidable.
- `ruff` for linting (replaces flake8/isort), `black` for formatting.
- `mypy` must pass with no errors on `src/`.
- Max line length: 88 (black default).
- Docstrings on public functions and classes only — keep them concise.

---

## What NOT to Do

- Do not call the external API from `service.py` or `database.py`.
- Do not use `os.getenv()` outside of `config.py`.
- Do not use Pydantic v1 APIs.
- Do not hardcode `"Access-Token"` in more than one place.
- Do not commit `.env`.
- Do not use `print()` — use `logger`.
- Do not crash on unknown fields or malformed records — log and skip.
- Do not duplicate employees on repeated fetches — upsert by `id`.

---

## Session Initialization Requirement

Read CLAUDE.md fully before doing anything. Confirm you have understood:
- the project architecture
- which files are responsible for what
- the critical rules section
- what is explicitly forbidden

Then tell me which phase we are working on today and what you will do next.
