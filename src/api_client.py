"""External API client: authentication, token caching, and employee fetch.

This is the only module that talks to the external API. The auth header name is
abstracted behind a single constant so switching schemes is a one-line change.
"""

import logging
from datetime import datetime, timezone
from typing import Any

import httpx
from tenacity import (
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

from src.config import Settings, settings

logger = logging.getLogger(__name__)

# Single source of truth for the (non-standard) auth header. Switching to
# `Authorization: Bearer {token}` should be a change confined to this module.
AUTH_HEADER_NAME = "Access-Token"


def _auth_headers(token: str) -> dict[str, str]:
    return {AUTH_HEADER_NAME: token}


def _is_token_valid(expires_at: str) -> bool:
    """Return True if the token's expiry is still in the future."""
    return datetime.fromisoformat(expires_at) > datetime.now(timezone.utc)


def _is_retryable(exc: BaseException) -> bool:
    """Retry only on 5xx responses and network-level errors, never on 4xx."""
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code >= 500
    return isinstance(exc, httpx.NetworkError)


class APIClient:
    """Stateful client for the external employee API.

    Owns its own token cache so multiple instances are independent and tests
    require no module-global cleanup.
    """

    def __init__(self, cfg: Settings) -> None:
        self._cfg = cfg
        self._token: str | None = None
        self._expires_at: str | None = None

    def authenticate(self) -> tuple[str, str]:
        """Authenticate and return (token, expires_at)."""
        url = f"{self._cfg.api_base_url}/api/token/"
        payload = {
            "grant_type": "password",
            "client_id": self._cfg.api_client_id,
            "client_secret": self._cfg.api_client_secret,
            "username": self._cfg.api_username,
            "password": self._cfg.api_password,
        }
        logger.debug("Authenticating against %s", url)
        response = httpx.post(url, json=payload)
        response.raise_for_status()
        data: dict[str, Any] = response.json()
        token: str = data["access_token"]
        expires_at: str = data["expires_at"]
        logger.info("Authenticated successfully; token expires at %s", expires_at)
        return token, expires_at

    def _get_token(self) -> str:
        """Return a valid token, re-authenticating if missing or expired."""
        if (
            self._token is not None
            and self._expires_at is not None
            and _is_token_valid(self._expires_at)
        ):
            logger.debug("Reusing cached token")
            return self._token
        logger.debug("Token missing or expired; re-authenticating")
        self._token, self._expires_at = self.authenticate()
        return self._token

    @retry(
        retry=retry_if_exception(_is_retryable),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        reraise=True,
    )
    def fetch_employees(self) -> list[dict[str, Any]]:
        """Fetch all employees using a cached (or freshly minted) token.

        Retries up to 3 times on 5xx/network errors with exponential backoff;
        4xx errors propagate immediately.
        """
        token = self._get_token()
        url = f"{self._cfg.api_base_url}/api/employee/list/"
        logger.debug("Fetching employees from %s", url)
        response = httpx.get(url, headers=_auth_headers(token))
        response.raise_for_status()
        employees: list[dict[str, Any]] = response.json()
        logger.info("Fetched %d employee records", len(employees))
        return employees


# Module-level singleton. fetch_cmd.py imports this directly.
client = APIClient(settings)
