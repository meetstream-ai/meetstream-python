"""HTTP transport for the MeetStream API.

Handles auth, retries, timeouts and the two MeetStream status codes that are
not failures.

Note the auth scheme: the REST API uses ``Authorization: Token <key>``. The MCP
server at mcp.meetstream.ai uses ``Bearer`` instead. They are not
interchangeable, and sending the wrong one returns 401.
"""
from __future__ import annotations

import os
import random
import time
from typing import Any, Dict, Mapping, Optional

import httpx

from ._errors import ConnectionError as MSConnectionError
from ._errors import MeetStreamError
from ._errors import TimeoutError as MSTimeoutError
from ._errors import error_for_status

DEFAULT_BASE_URL = "https://api.meetstream.ai/api/v1"
RETRYABLE = frozenset({408, 429, 500, 502, 503, 504})
_USER_AGENT = "meetstream-python"


def _message_from(body: Any, status: int) -> str:
    """Pull out the API's own ``message``, falling back to something useful."""
    if isinstance(body, Mapping):
        for key in ("message", "detail", "error"):
            value = body.get(key)
            if isinstance(value, str) and value:
                return value
    if isinstance(body, str) and body.strip():
        return body.strip()[:500]
    return f"MeetStream API returned HTTP {status}"


def _resolve_key(api_key: Optional[str]) -> str:
    key = api_key or os.environ.get("MEETSTREAM_API_KEY")
    if not key:
        raise MeetStreamError(
            "Missing MeetStream API key. Pass api_key=... or set MEETSTREAM_API_KEY. "
            "Create a key at https://app.meetstream.ai/api-key"
        )
    return key


def _backoff(attempt: int, retry_after: Optional[float]) -> float:
    if retry_after is not None:
        return retry_after
    return (2 ** attempt) * 0.5 + random.random() * 0.25


class BaseTransport:
    """Shared config and response handling for the sync and async clients."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        *,
        base_url: Optional[str] = None,
        timeout: float = 60.0,
        max_retries: int = 2,
        default_headers: Optional[Dict[str, str]] = None,
    ) -> None:
        self.api_key = _resolve_key(api_key)
        self.base_url = (base_url or os.environ.get("MEETSTREAM_API_URL") or DEFAULT_BASE_URL).rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries
        self.default_headers = dict(default_headers or {})

    def _headers(self, idempotency_key: Optional[str], extra: Optional[Mapping[str, str]]) -> Dict[str, str]:
        headers = {
            "Authorization": f"Token {self.api_key}",
            "Accept": "application/json",
            "User-Agent": _USER_AGENT,
        }
        headers.update(self.default_headers)
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key
        if extra:
            headers.update(extra)
        return headers

    def _url(self, path: str) -> str:
        return self.base_url + (path if path.startswith("/") else "/" + path)

    @staticmethod
    def _parse(response: httpx.Response) -> Any:
        if not response.content:
            return None
        try:
            return response.json()
        except ValueError:
            return response.text

    def _handle(self, response: httpx.Response) -> Any:
        """Turn a response into a value or an exception.

        202 sits inside the 2xx range, so it must be checked *before* the
        success check or "not ready yet" would silently look like success. 507
        is the mirror case: outside 2xx, but an idempotent replay and therefore
        a success.
        """
        parsed = self._parse(response)
        status = response.status_code

        if status != 202 and (response.is_success or status == 507):
            return parsed

        retry_after_raw = response.headers.get("retry-after")
        try:
            retry_after = float(retry_after_raw) if retry_after_raw else None
        except ValueError:
            retry_after = None

        raise error_for_status(
            status,
            _message_from(parsed, status),
            body=parsed,
            request_id=response.headers.get("x-request-id"),
            retry_after=retry_after,
        )


class MeetStreamTransport(BaseTransport):
    """Synchronous transport."""

    def __init__(self, *args: Any, http_client: Optional[httpx.Client] = None, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._client = http_client or httpx.Client(timeout=self.timeout)
        self._owns_client = http_client is None

    def request(
        self,
        method: str,
        path: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        json: Any = None,
        idempotency_key: Optional[str] = None,
        headers: Optional[Mapping[str, str]] = None,
        timeout: Optional[float] = None,
        max_retries: Optional[int] = None,
    ) -> Any:
        retries = self.max_retries if max_retries is None else max_retries
        clean_params = {k: v for k, v in (params or {}).items() if v is not None}
        last_exc: Optional[MeetStreamError] = None

        for attempt in range(retries + 1):
            try:
                response = self._client.request(
                    method,
                    self._url(path),
                    params=clean_params or None,
                    json=json,
                    headers=self._headers(idempotency_key, headers),
                    timeout=timeout if timeout is not None else self.timeout,
                )
            except httpx.TimeoutException as exc:
                last_exc = MSTimeoutError(f"Request timed out: {method} {path} ({exc})")
                if attempt == retries:
                    raise last_exc from exc
                time.sleep(_backoff(attempt, None))
                continue
            except httpx.HTTPError as exc:
                last_exc = MSConnectionError(f"Could not reach the MeetStream API: {exc}")
                if attempt == retries:
                    raise last_exc from exc
                time.sleep(_backoff(attempt, None))
                continue

            try:
                return self._handle(response)
            except MeetStreamError as exc:
                # 202 is never retried here: the caller decides the polling
                # cadence through the wait_for_* helpers.
                if response.status_code not in RETRYABLE or attempt == retries:
                    raise
                last_exc = exc
                time.sleep(_backoff(attempt, getattr(exc, "retry_after", None)))

        raise last_exc or MeetStreamError("Request failed")

    def get(self, path: str, **kw: Any) -> Any:
        return self.request("GET", path, **kw)

    def post(self, path: str, json: Any = None, **kw: Any) -> Any:
        return self.request("POST", path, json=json, **kw)

    def put(self, path: str, json: Any = None, **kw: Any) -> Any:
        return self.request("PUT", path, json=json, **kw)

    def patch(self, path: str, json: Any = None, **kw: Any) -> Any:
        return self.request("PATCH", path, json=json, **kw)

    def delete(self, path: str, **kw: Any) -> Any:
        return self.request("DELETE", path, **kw)

    def close(self) -> None:
        if self._owns_client:
            self._client.close()


class AsyncMeetStreamTransport(BaseTransport):
    """Asynchronous transport. Mirrors the sync API exactly."""

    def __init__(self, *args: Any, http_client: Optional[httpx.AsyncClient] = None, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._client = http_client or httpx.AsyncClient(timeout=self.timeout)
        self._owns_client = http_client is None

    async def request(
        self,
        method: str,
        path: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        json: Any = None,
        idempotency_key: Optional[str] = None,
        headers: Optional[Mapping[str, str]] = None,
        timeout: Optional[float] = None,
        max_retries: Optional[int] = None,
    ) -> Any:
        import asyncio

        retries = self.max_retries if max_retries is None else max_retries
        clean_params = {k: v for k, v in (params or {}).items() if v is not None}
        last_exc: Optional[MeetStreamError] = None

        for attempt in range(retries + 1):
            try:
                response = await self._client.request(
                    method,
                    self._url(path),
                    params=clean_params or None,
                    json=json,
                    headers=self._headers(idempotency_key, headers),
                    timeout=timeout if timeout is not None else self.timeout,
                )
            except httpx.TimeoutException as exc:
                last_exc = MSTimeoutError(f"Request timed out: {method} {path} ({exc})")
                if attempt == retries:
                    raise last_exc from exc
                await asyncio.sleep(_backoff(attempt, None))
                continue
            except httpx.HTTPError as exc:
                last_exc = MSConnectionError(f"Could not reach the MeetStream API: {exc}")
                if attempt == retries:
                    raise last_exc from exc
                await asyncio.sleep(_backoff(attempt, None))
                continue

            try:
                return self._handle(response)
            except MeetStreamError as exc:
                if response.status_code not in RETRYABLE or attempt == retries:
                    raise
                last_exc = exc
                await asyncio.sleep(_backoff(attempt, getattr(exc, "retry_after", None)))

        raise last_exc or MeetStreamError("Request failed")

    async def get(self, path: str, **kw: Any) -> Any:
        return await self.request("GET", path, **kw)

    async def post(self, path: str, json: Any = None, **kw: Any) -> Any:
        return await self.request("POST", path, json=json, **kw)

    async def put(self, path: str, json: Any = None, **kw: Any) -> Any:
        return await self.request("PUT", path, json=json, **kw)

    async def patch(self, path: str, json: Any = None, **kw: Any) -> Any:
        return await self.request("PATCH", path, json=json, **kw)

    async def delete(self, path: str, **kw: Any) -> Any:
        return await self.request("DELETE", path, **kw)

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()
