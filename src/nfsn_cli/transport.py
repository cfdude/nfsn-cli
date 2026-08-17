"""HTTP transport for the NearlyFreeSpeech.NET API.

Per NFSN's API/Introduction page:

* Property reads are ``GET``; the value comes back in the response body.
* Property writes are ``PUT``; the **raw request body** becomes the new value.
* Method calls are ``POST`` with an ``application/x-www-form-urlencoded`` body.
* Errors are 4XX/5XX with a JSON body carrying ``error`` and ``debug`` keys.
* Responses are sometimes JSON and sometimes a bare string, under the
  ``application/x-nfsn-api`` content type.
"""

from __future__ import annotations

import json
import time
from email.utils import parsedate_to_datetime
from typing import Any, Self
from urllib.parse import urlencode

import httpx

from nfsn_cli.auth import auth_header
from nfsn_cli.config import Credentials

API_BASE = "https://api.nearlyfreespeech.net"

# NFSN rejects requests whose timestamp is more than 5 seconds off its own clock.
MAX_CLOCK_SKEW_SECONDS = 5


class NfsnError(RuntimeError):
    """An error returned by the API, or a malformed response."""


class NfsnAuthError(NfsnError):
    """Authentication failed (HTTP 401)."""


class NfsnClockSkewError(NfsnError):
    """The local clock is too far from NFSN's for any request to be accepted."""


class NfsnTransport:
    def __init__(
        self,
        credentials: Credentials,
        *,
        base_url: str = API_BASE,
        transport: httpx.BaseTransport | None = None,
        timeout: float = 30.0,
    ) -> None:
        self._credentials = credentials
        self._base_url = base_url.rstrip("/")
        self._client = httpx.Client(transport=transport, timeout=timeout)

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def close(self) -> None:
        self._client.close()

    # -- verbs ---------------------------------------------------------------

    def get(self, path: str) -> Any:
        """Read a property."""
        return self._request("GET", path, body=b"")

    def put(self, path: str, value: object) -> Any:
        """Write a property. The raw body becomes the new value."""
        return self._request("PUT", path, body=str(value).encode("utf-8"))

    def post(self, path: str, params: dict[str, str] | None = None) -> Any:
        """Call a method."""
        body = urlencode(params or {}).encode("utf-8")
        return self._request(
            "POST",
            path,
            body=body,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )

    # -- plumbing ------------------------------------------------------------

    def _request(
        self,
        method: str,
        path: str,
        *,
        body: bytes,
        headers: dict[str, str] | None = None,
    ) -> Any:
        request_headers = {
            "X-NFSN-Authentication": auth_header(
                self._credentials.login,
                self._credentials.api_key,
                path,
                body.decode("utf-8"),
            ),
            "Accept": "application/json",
            **(headers or {}),
        }
        response = self._client.request(
            method, f"{self._base_url}{path}", content=body, headers=request_headers
        )
        if response.status_code >= 400:
            self._raise_for_response(response, path)
        return _decode(response)

    def _raise_for_response(self, response: httpx.Response, path: str) -> None:
        detail = _error_detail(response)
        skew = _clock_skew(response)
        if skew is not None and abs(skew) > MAX_CLOCK_SKEW_SECONDS:
            raise NfsnClockSkewError(
                f"Local clock is {skew:+.0f}s from NFSN's, which exceeds their "
                f"{MAX_CLOCK_SKEW_SECONDS}s tolerance. Sync your clock (NTP) and retry. "
                f"Server said: {detail}"
            )
        if response.status_code == 401:
            raise NfsnAuthError(
                f"Authentication rejected for {path}. Check NFSN_LOGIN and NFSN_API_KEY. "
                f"Server said: {detail}"
            )
        raise NfsnError(f"{response.status_code} from {path}: {detail}")


def _clock_skew(response: httpx.Response) -> float | None:
    """Seconds our clock is ahead of the server's, from the Date header."""
    raw = response.headers.get("date")
    if not raw:
        return None
    try:
        server_time = parsedate_to_datetime(raw).timestamp()
    except (TypeError, ValueError):
        return None
    return time.time() - server_time


def _decode(response: httpx.Response) -> Any:
    """NFSN returns JSON for most calls and a bare string for some. Empty means success."""
    if not response.content:
        return None
    try:
        return json.loads(response.text)
    except json.JSONDecodeError:
        # Documented behaviour: some calls answer with a plain string, not JSON.
        return response.text.strip()


def _error_detail(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except json.JSONDecodeError:
        return response.text[:300] or "(empty response body)"
    if isinstance(payload, dict):
        parts = [str(payload[key]) for key in ("error", "debug") if payload.get(key)]
        if parts:
            return " | ".join(parts)
    return str(payload)[:300]
