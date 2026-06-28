import json
from collections.abc import Iterator
from datetime import datetime, timedelta, timezone

import httpx
import pytest
import respx

from src.api_client import APIClient
from src.config import settings

# The test server is provided by respx, which mocks out the external API. The
# URLs below are used to register mock routes. The actual base URL is irrelevant
# because respx intercepts all requests and returns the mocked responses.
BASE_URL = "http://testserver"
TOKEN_URL = f"{BASE_URL}/api/token/"
EMPLOYEES_URL = f"{BASE_URL}/api/employee/list/"


def _future_iso() -> str:
    return (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()


def _past_iso() -> str:
    return (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()


@pytest.fixture
def client() -> APIClient:
    """Fresh APIClient per test — each instance has its own empty token cache."""
    return APIClient(settings)


@pytest.fixture(autouse=True)
def no_retry_sleep() -> Iterator[None]:
    """Skip tenacity backoff sleeps so retry tests run instantly."""
    original = APIClient.fetch_employees.retry.sleep  # type: ignore[attr-defined]
    APIClient.fetch_employees.retry.sleep = lambda *args, **kwargs: None  # type: ignore[attr-defined]
    yield
    APIClient.fetch_employees.retry.sleep = original  # type: ignore[attr-defined]


@respx.mock
def test_authenticate_success(client: APIClient) -> None:
    expires_at = _future_iso()
    route = respx.post(TOKEN_URL).mock(
        return_value=httpx.Response(
            200, json={"access_token": "abc123", "expires_at": expires_at}
        )
    )
    token, returned_expires = client.authenticate()

    assert route.called
    assert token == "abc123"
    assert returned_expires == expires_at

    # The POST body must carry exactly the five spec fields, with grant_type
    # hardcoded to "password" and the credentials sourced from settings.
    sent_body = json.loads(route.calls[0].request.content)
    assert sent_body == {
        "grant_type": "password",
        "client_id": settings.api_client_id,
        "client_secret": settings.api_client_secret,
        "username": settings.api_username,
        "password": settings.api_password,
    }


@respx.mock
def test_fetch_sends_access_token_header(client: APIClient) -> None:
    respx.post(TOKEN_URL).mock(
        return_value=httpx.Response(
            200, json={"access_token": "abc123", "expires_at": _future_iso()}
        )
    )
    employees_route = respx.get(EMPLOYEES_URL).mock(
        return_value=httpx.Response(200, json=[])
    )

    client.fetch_employees()

    # The fetch must carry the non-standard Access-Token header with the token.
    assert employees_route.calls[0].request.headers["Access-Token"] == "abc123"


@respx.mock
def test_token_cached_on_second_fetch(client: APIClient) -> None:
    token_route = respx.post(TOKEN_URL).mock(
        return_value=httpx.Response(
            200, json={"access_token": "abc123", "expires_at": _future_iso()}
        )
    )
    employees_route = respx.get(EMPLOYEES_URL).mock(
        return_value=httpx.Response(200, json=[{"id": "1"}])
    )

    client.fetch_employees()
    client.fetch_employees()

    # Authenticated once, reused the cached token on the second fetch.
    assert token_route.call_count == 1
    assert employees_route.call_count == 2


@respx.mock
def test_expired_token_triggers_reauthentication(client: APIClient) -> None:
    client._token = "stale-token"
    client._expires_at = _past_iso()

    token_route = respx.post(TOKEN_URL).mock(
        return_value=httpx.Response(
            200, json={"access_token": "fresh-token", "expires_at": _future_iso()}
        )
    )
    respx.get(EMPLOYEES_URL).mock(return_value=httpx.Response(200, json=[]))

    client.fetch_employees()

    assert token_route.call_count == 1


@respx.mock
def test_500_triggers_retry(client: APIClient) -> None:
    respx.post(TOKEN_URL).mock(
        return_value=httpx.Response(
            200, json={"access_token": "abc123", "expires_at": _future_iso()}
        )
    )
    employees_route = respx.get(EMPLOYEES_URL).mock(
        return_value=httpx.Response(500, json={"error": "boom"})
    )

    with pytest.raises(httpx.HTTPStatusError):
        client.fetch_employees()

    # 3 attempts total before the original error is re-raised.
    assert employees_route.call_count == 3


@respx.mock
def test_network_error_triggers_retry(client: APIClient) -> None:
    respx.post(TOKEN_URL).mock(
        return_value=httpx.Response(
            200, json={"access_token": "abc123", "expires_at": _future_iso()}
        )
    )
    employees_route = respx.get(EMPLOYEES_URL).mock(
        side_effect=httpx.ConnectError("connection refused")
    )

    with pytest.raises(httpx.ConnectError):
        client.fetch_employees()

    # Network-level errors are transient: retried up to the attempt limit.
    assert employees_route.call_count == 3


@respx.mock
def test_4xx_is_not_retried(client: APIClient) -> None:
    respx.post(TOKEN_URL).mock(
        return_value=httpx.Response(
            200, json={"access_token": "abc123", "expires_at": _future_iso()}
        )
    )
    employees_route = respx.get(EMPLOYEES_URL).mock(
        return_value=httpx.Response(422, json={"error": "bad request"})
    )

    with pytest.raises(httpx.HTTPStatusError):
        client.fetch_employees()

    # 4xx is a caller error: fail fast, no retries.
    assert employees_route.call_count == 1


@respx.mock
def test_auth_401_raises(client: APIClient) -> None:
    route = respx.post(TOKEN_URL).mock(
        return_value=httpx.Response(401, json={"error": "unauthorized"})
    )

    with pytest.raises(httpx.HTTPStatusError):
        client.authenticate()

    assert route.call_count == 1
