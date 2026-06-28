# Data Import Service

[![CI](https://github.com/bozhinovristo/data-import-service/actions/workflows/ci.yml/badge.svg)](https://github.com/bozhinovristo/data-import-service/actions/workflows/ci.yml)

A small Python application that authenticates against an external API, fetches a list of employees, validates and stores them in SQLite, and exposes them through a read-only FastAPI HTTP service.

The service **never proxies the external API** — it serves only what has already
been fetched and stored locally.

---

## Table of Contents
- [Requirements](#requirements)
- [Setup](#setup)
- [Usage](#usage)
- [API](#api)
- [Authentication](#authentication)
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

## Authentication

This project has **two independent boundaries**, and only one of them uses a token.

### Outbound — authenticating to the external test server

`src/api_client.py` is the only component that talks to the external API (the
"Test Server on localhost"). It uses a password-grant token flow:

1. **Obtain a token** — POST to `{API_BASE_URL}/api/token/` with a body built from
   the four credential env vars:

   ```json
   {
     "grant_type": "password",
     "client_id": "${API_CLIENT_ID}",
     "client_secret": "${API_CLIENT_SECRET}",
     "username": "${API_USERNAME}",
     "password": "${API_PASSWORD}"
   }
   ```

   The response returns `access_token` and `expires_at`.

2. **Cache it** — the token and its expiry are held in memory on the `APIClient`
   instance; no token is ever written to disk.

3. **Use it** — every employee fetch sends the token in the non-standard header
   `Access-Token: {access_token}`. The header name is abstracted behind the single
   `AUTH_HEADER_NAME` constant, so switching to `Authorization: Bearer {token}` is a
   one-line change.

4. **Refresh automatically** — before each fetch the client checks `expires_at`; if
   the token is missing or expired it re-authenticates, otherwise it reuses the
   cached token.

This flow runs only when you fetch real data via `poetry run python -m src.fetch_cmd`.

#### Credentials

The four `API_*` values are **issued together with the test server** and are
intentionally left **blank** in `.env.example`. Fill them into your local `.env`
before running `fetch_cmd`:

```
API_CLIENT_ID=...
API_CLIENT_SECRET=...
API_USERNAME=...
API_PASSWORD=...
```

You do **not** need real credentials to run the service or seed demo data — neither
path calls the external API (see below).

#### Running the flow end-to-end without the real server

The real test server is provided separately by whoever issues the test. To exercise
the **live** auth → fetch → store → serve pipeline without it, a self-contained stub
that implements the two endpoints with the same contract is included at
[`dev/mock_server.py`](dev/mock_server.py) — a local testing aid, not part of the app.

1. **Start the stub** (leave it running in its own terminal):

   ```bash
   poetry run uvicorn dev.mock_server:app --port 8001
   ```

2. **Point the app at it** — in `.env`, set the base URL (the four `API_*`
   credentials may stay blank; the stub ignores them):

   ```
   API_BASE_URL=http://localhost:8001
   ```

3. **Run the real fetch pipeline**, then serve and read the data back:

   ```bash
   poetry run python -m src.fetch_cmd          # live auth → fetch → store
   poetry run uvicorn src.service:app --port 8000
   curl "http://localhost:8000/employees"      # the fetched employees
   ```

Or exercise the stub's auth endpoints directly:

```bash
# Issue a token (any/empty credentials are accepted)
curl -X POST http://localhost:8001/api/token/ -H "Content-Type: application/json" -d "{}"

# Use it on the protected endpoint
curl http://localhost:8001/api/employee/list/ -H "Access-Token: stub-access-token"

# Omit the token -> 401 (the Access-Token header is enforced)
curl -i http://localhost:8001/api/employee/list/
```

When you receive the real server, set `API_BASE_URL=http://localhost` (port 80) and
start it instead — the same `fetch_cmd` runs against it unchanged.

#### Demo UI (login + employee table)

A minimal browser UI under [`frontend/`](frontend/) demonstrates the auth flow:
a login screen that authenticates against the test server, then a table of the
employees from `/api/employee/list/`. It is plain HTML/CSS/JS (no build step) and
talks **only** to the test server.

```bash
# 1. Start the (mock) test server
poetry run uvicorn dev.mock_server:app --port 8001

# 2. Serve the UI (in another terminal)
make ui                       # python -m http.server 5500 --directory frontend
```

Open <http://localhost:5500> and log in with the test user **`testuser` /
`testpass`** (the mock server accepts any credentials). To point the UI at the real
server, change `API_BASE_URL` at the top of [`frontend/app.js`](frontend/app.js).

### Inbound — the HTTP service is intentionally unauthenticated

The FastAPI service (`GET /employees`, `GET /employees/{id}`) has **no
authentication**, by design. The brief only requires it to serve locally stored
employees from local storage; it never asks for the service itself to be protected,
and the token flow exists purely for *consuming* the external API. That is why
`curl http://localhost:8000/employees` returns data without any token.

Because the service never touches the external API, it also runs fine with the
`API_*` values left blank — they are read only when building the outbound token
request.

#### Optional: gate the service with an API key

If you wanted to protect the service (an extension beyond the brief), the same
blank-value pattern extends naturally — add a `SERVICE_API_KEY` setting to
`config.py`, then require it via a FastAPI dependency:

```python
from fastapi import Depends, Header, HTTPException

def require_api_key(x_api_key: str = Header(default="")) -> None:
    if not settings.service_api_key or x_api_key != settings.service_api_key:
        raise HTTPException(status_code=401, detail="Invalid API key")
```

Attach it with `dependencies=[Depends(require_api_key)]` on the routes (or the whole
app). Left unset/blank, the service stays open — matching the current,
spec-compliant default.

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

### Make targets

Common tasks are wrapped in a `Makefile` (requires GNU `make`):

```bash
make install   # poetry install
make fetch     # fetch from the API and store
make seed      # seed demo data + export employees.json / .csv
make run       # run the service on :8000
make test      # run the test suite
make gate      # lint + format-check + typecheck + test
```

### Docker

```bash
make docker-build      # or: docker build -t data-import-service .
make docker-run        # serves the API on :8000, reading env from .env
```

The image installs runtime dependencies only and serves the API with uvicorn;
all required environment variables are supplied at run time via `--env-file .env`.

---

## Architecture

```
External API
    │
    ▼
api_client.py   ← authenticate, token cache + expiry, async fetch (httpx.AsyncClient), retries (tenacity)
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

## Rationale

Why the key technical decisions were made, and the trade-offs accepted.

- **FastAPI for the service.** The brief prefers it, and it pays off here: automatic
  OpenAPI docs at `/docs`, request validation/coercion of query params for free, and
  `Depends` for clean per-request resource management (a fresh DB connection per
  request). *Trade-off:* a heavier dependency than Flask, accepted for the built-in
  validation and docs.
- **Stdlib `sqlite3`, not an ORM.** The data is a single flat table with an
  `INSERT OR REPLACE` upsert keyed on `id`; an ORM (SQLAlchemy) would add a dependency
  and indirection for no real gain at this scope. *Trade-off:* hand-written SQL and a
  manual sort allowlist instead of ORM query building — kept safe by binding all values
  and validating `sort` against `ALLOWED_SORT_FIELDS`. Migrating to Postgres/SQLAlchemy
  later would be localized to `database.py`.
- **Async `httpx` + `tenacity`.** The API client uses `httpx.AsyncClient`, and the
  fetch pipeline is `async`, run from the CLI via `asyncio.run()` behind a thin sync
  `main()`. `tenacity` drives the retries async-aware (the same exponential backoff,
  scoped to 5xx + network errors only). *Boundary:* async is applied to the
  network-bound fetch, **not** the read path — `service.py` and `database.py` stay
  synchronous because SQLite is a blocking local driver and FastAPI already runs sync
  handlers in a threadpool, so making them `async def` over a blocking driver would
  stall the event loop. Async where it helps (I/O-bound HTTP), sync where it doesn't
  (local disk).
- **Pydantic v2 for the model.** Validation and type normalization belong at the
  ingestion boundary: `EmailStr`, a real `date` for `date_of_birth`, and a
  `mode="before"` validator that coerces the API's stringified `rating` to `float`.
  Unknown fields are tolerated (`extra="ignore"`) but logged, so the importer never
  crashes on a schema drift yet stays traceable.
- **Fetch and serve are fully decoupled.** `service.py` reads only the local DB and
  never imports `api_client.py`, so a request can never trigger an outbound API call.
  This directly satisfies the brief's "do not proxy the external API on each request"
  and keeps the read path fast and deterministic.
- **Caller-owned transactions.** `database.upsert_employee` deliberately does not
  commit; `fetch_cmd` commits once after the batch, making a run atomic — a mid-batch
  failure leaves no partial state.
- **Token caching with expiry + a single auth-header constant.** The token is cached
  in memory and reused until `expires_at`, then re-minted automatically — avoiding a
  re-auth on every call while respecting expiry. The non-standard `Access-Token` header
  lives in one constant (`AUTH_HEADER_NAME`), so switching to `Authorization: Bearer`
  is a one-line change.
- **Config only through `config.py`.** All env vars are read in one place via
  `pydantic-settings`, which fails fast at startup if any required variable is missing
  and keeps secrets out of source and out of scattered `os.getenv` calls.
- **The HTTP service is intentionally unauthenticated.** The brief asks it only to serve
  locally stored employees; adding auth would be scope the spec doesn't request. The
  optional API-key pattern is documented above for when that changes.

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
