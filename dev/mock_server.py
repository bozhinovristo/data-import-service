"""Local stand-in for the external test server — DEV ONLY, not part of the app.

The real API (the "Test Server on localhost") is provided separately by whoever
issues the technical test. When you don't have it, run this stub to exercise the
full auth -> fetch -> store -> serve pipeline against a real HTTP server:

    poetry run uvicorn dev.mock_server:app --port 8001

Then point the app at it by setting `API_BASE_URL=http://localhost:8001` in `.env`
and run `poetry run python -m src.fetch_cmd`.

It implements the two documented endpoints with the same contract as the brief:
a password-grant token endpoint and a token-protected employee list. It is fully
self-contained (no `src` imports), so it starts even with an empty `.env`.
"""

from datetime import datetime, timedelta, timezone

from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="Mock Test Server (dev only)")

# Permissive CORS so the browser demo UI (served from a static server on another
# port) can call this stub. Dev-only: a real server would whitelist origins.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # dev stub only
    allow_credentials=False,  # the token travels in a header, not a cookie
    allow_methods=["*"],
    allow_headers=["*"],  # allows the custom Access-Token header + preflight
)

# The token this stub issues and then requires on the employee endpoint. A real
# server would mint a random token; a fixed value keeps the round-trip easy to see.
_ACCESS_TOKEN = "stub-access-token"

# Employee records in the API's shape — note `rating` is a string, exactly as the
# real API returns it, so the fetch path exercises the same float coercion.
_EMPLOYEES: list[dict[str, str]] = [
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
        "bio": "Sample employee served by the mock test server.",
        "rating": "3.0600000000000001",
    },
    {
        "id": "2a3b4c5d-6e7f-8091-a2b3-c4d5e6f70819",
        "date_of_birth": "1992-11-03",
        "image": "https://example.com/img/2.png",
        "email": "bob.jones@example.com",
        "first_name": "Bob",
        "last_name": "Jones",
        "title": "Mr.",
        "address": "55 King Street West",
        "country": "Canada",
        "bio": "Another sample employee.",
        "rating": "2.9",
    },
    {
        "id": "4c5d6e7f-8091-a2b3-c4d5-e6f708192031",
        "date_of_birth": "1995-04-09",
        "image": "https://example.com/img/3.png",
        "email": "yuki.tanaka@example.com",
        "first_name": "Yuki",
        "last_name": "Tanaka",
        "title": "Ms.",
        "address": "2-1-1 Nihonbashi",
        "country": "Japan",
        "bio": "A third sample employee.",
        "rating": "4.95",
    },
]


@app.post("/api/token/")
def issue_token() -> dict[str, str]:
    """Password-grant stub: returns a bearer token valid for one hour.

    The request body is accepted but not validated — any credentials work, which
    is what lets you run the flow without the real server's secrets.
    """
    expires_at = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
    return {
        "access_token": _ACCESS_TOKEN,
        "token_type": "bearer",
        "expires_at": expires_at,
    }


@app.get("/api/employee/list/")
def list_employees(access_token: str = Header(default="")) -> list[dict[str, str]]:
    """Return the demo employees, but only when the Access-Token header is valid."""
    if access_token != _ACCESS_TOKEN:
        raise HTTPException(status_code=401, detail="Missing or invalid Access-Token")
    return _EMPLOYEES
