# Data Import Service

A small Python application that authenticates against an external API, fetches a list of employees, validates and stores them in SQLite, and exposes them through a read-only FastAPI HTTP service.

The service **never proxies the external API** — it serves only what has already
been fetched and stored locally.

---

## Table of Contents
- [Requirements](#requirements)
- [Setup](#setup)
- [Usage](#usage)
- [API](#api)
- [Development](#development)
- [Architecture](#architecture)
- [Design Notes & Assumptions](#design-notes--assumptions)

---

## Requirements

- Python **3.11+**
- [Poetry](https://python-poetry.org/) for dependency management

---

## Setup

```bash
# 1. Install dependencies (creates a virtualenv)
poetry install

# 2. Create your local env file from the template and fill in credentials
cp .env.example .env        # Windows: copy .env.example .env
```

### Environment variables

All configuration is loaded exclusively through `src/config.py` using
`pydantic-settings`. Every variable is **required** — the app refuses to start if
any is missing. Secrets live only in `.env`, which is git-ignored; `.env.example`
is the committed template.

| Variable | Description | Example |
|---|---|---|
| `API_BASE_URL` | Base URL of the external API | `http://localhost` |
| `API_CLIENT_ID` | OAuth client id | |
| `API_CLIENT_SECRET` | OAuth client secret | |
| `API_USERNAME` | Resource-owner username | |
| `API_PASSWORD` | Resource-owner password | |
| `DATABASE_URL` | SQLAlchemy-style SQLite URL | `sqlite:///./employees.db` |

---

## Usage

### 1. Fetch and store data

Authenticates, fetches the employee list, validates each record, and upserts it
into the SQLite database. Malformed records are logged and skipped; the rest are
committed as a single transaction.

```bash
poetry run python -m src.fetch_cmd
```

### 2. Seed demo data (no API required)

Populates the database with a small set of realistic demo employees and writes
`employees.json` / `employees.csv` snapshots **from the database**. Useful for
trying the service without access to the external API.

```bash
poetry run python -m src.seed_cmd
```

### 3. Run the HTTP service

```bash
poetry run uvicorn src.service:app --reload --port 8000
```

Interactive OpenAPI docs are then available at <http://localhost:8000/docs>.

---

## API

### `GET /employees`

Returns locally stored employees. Reads only from SQLite.

| Query param | Type | Description |
|---|---|---|
| `country` | string | Exact match, case-sensitive |
| `min_rating` | float | Inclusive lower bound on `rating` |
| `sort` | string | One of `first_name`, `last_name`, `rating`, `date_of_birth` |
| `format` | string | `json` (default) or `csv` |
| `limit` | int | Pagination size (default 100, 1–1000) |
| `offset` | int | Pagination offset (default 0) |

```bash
# All employees (JSON)
curl "http://localhost:8000/employees"

# Filter by country and minimum rating, sorted by rating
curl "http://localhost:8000/employees?country=USA&min_rating=3.5&sort=rating"

# CSV export (downloads employees.csv)
curl -OJ "http://localhost:8000/employees?format=csv"

# Pagination
curl "http://localhost:8000/employees?limit=20&offset=40"
```

### `GET /employees/{id}`

Returns a single employee by id, or `404` if not found.

```bash
curl "http://localhost:8000/employees/8c8c13b6-35ed-3ffb-92d5-c438825df67f"
```

---

## Sample outputs

`employees.json` and `employees.csv` in the repository root are snapshots
generated from the seeded database (see [`src/seed_cmd.py`](src/seed_cmd.py)).
Regenerate them at any time with `poetry run python -m src.seed_cmd`.

---

## Development

```bash
# Run all tests
poetry run pytest

# Tests with coverage
poetry run pytest --cov=src --cov-report=term-missing

# Full quality gate (run before every commit)
poetry run ruff check . && poetry run black . && poetry run mypy src/
```

Tests never make real network calls — HTTP is mocked at the `httpx` transport
level with `respx`, and each test gets a fresh SQLite database.

---

## Architecture

```
External API
    │
    ▼
api_client.py   ← authenticate, token cache + expiry, fetch, retries (tenacity)
    │
    ▼
models.py       ← Pydantic v2 Employee model: validation + type normalization
    │
    ▼
database.py     ← SQLite upsert (by id), filtered/sorted/paginated queries
    │
    ▼
service.py      ← FastAPI: GET /employees, GET /employees/{id} (reads DB only)

config.py       ← loads/validates all env vars (pydantic-settings); used by all layers
fetch_cmd.py    ← CLI: auth → fetch → validate → store
seed_cmd.py     ← CLI: seed demo data → export JSON/CSV snapshots
```

| File | Responsibility |
|---|---|
| `src/config.py` | Load and validate all env vars via pydantic-settings. |
| `src/models.py` | Pydantic v2 `Employee` model + validation/normalization. |
| `src/api_client.py` | Auth, token caching, employee fetch, retries. |
| `src/database.py` | SQLite init, upsert, filtered queries. |
| `src/service.py` | FastAPI app, route handlers, CSV/JSON responses. |
| `src/fetch_cmd.py` | CLI entry point: auth → fetch → store. |
| `src/seed_cmd.py` | CLI entry point: seed demo data, export snapshots. |

---

## Design notes & assumptions

- **The service is strictly read-only.** `service.py` imports `database.py` only —
  never `api_client.py`. Fetching and serving are fully decoupled, so the HTTP
  layer can never accidentally hit the external API on a request path.
- **Non-standard auth header is abstracted.** The API expects `Access-Token: {token}`.
  This is confined to a single constant (`AUTH_HEADER_NAME`) in `api_client.py`, so
  switching to `Authorization: Bearer {token}` is a one-line change.
- **Token caching with expiry.** A cached token is reused until its `expires_at`
  passes, at which point the client re-authenticates automatically.
- **Retries are conservative.** `tenacity` retries with exponential backoff only on
  5xx responses and network errors. 4xx errors (caller mistakes) fail fast.
- **Type normalization.** The API returns `rating` as a string (e.g.
  `"3.0600000000000001"`); the `Employee` model coerces it to `float`. `id` is a
  UUID, `date_of_birth` a date, `email` a validated address.
- **Resilient ingestion.** Malformed records are logged and skipped rather than
  aborting the whole batch; unknown fields from the API are logged and tolerated
  (not stored). Empty result sets are handled without error. Repeated fetches
  upsert by `id`, so they never create duplicate rows.
- **Caller-owned transactions.** `database.upsert_employee` does not commit; the
  caller (e.g. `fetch_cmd`) commits once after a batch, so a run is atomic.
- **Per-request DB connections.** The service opens and closes a SQLite connection
  per request via a FastAPI dependency, keeping handlers stateless.
- **`fetched_at`** is stamped by the database layer on every upsert, recording when
  each record was last persisted.
