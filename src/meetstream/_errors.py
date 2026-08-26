"""Errors raised by the MeetStream SDK.

Every MeetStream error response carries a ``message`` field; it becomes
``error.message`` and the raw body is kept on ``error.body``.
"""
from __future__ import annotations

from typing import Any, Optional

__all__ = [
    "MeetStreamError", "ConnectionError", "TimeoutError", "BadRequestError",
    "AuthenticationError", "PermissionError", "NotFoundError", "ConflictError",
    "RateLimitError", "ServerError", "NotReadyError", "error_for_status",
]


class MeetStreamError(Exception):
    """Base class for everything this SDK raises."""

    def __init__(
        self,
        message: str,
        *,
        status: Optional[int] = None,
        body: Any = None,
        request_id: Optional[str] = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.status = status
        self.body = body
        self.request_id = request_id

    def __str__(self) -> str:  # pragma: no cover - trivial
        if self.status is not None:
            return f"[{self.status}] {self.message}"
        return self.message


class ConnectionError(MeetStreamError):
    """The request never reached the API, or the connection failed mid-flight."""


class TimeoutError(MeetStreamError):
    """The request exceeded the configured timeout."""


class BadRequestError(MeetStreamError):
    """400 - the request was malformed. Read ``message``; do not retry unchanged."""


class AuthenticationError(MeetStreamError):
    """401 - no API key was sent. The header is missing entirely."""


class PermissionError(MeetStreamError):  # noqa: A001 - deliberately shadows builtin
    """403 - a key was sent but rejected: wrong, revoked, or truncated."""


class NotFoundError(MeetStreamError):
    """404 - unknown bot id, transcript id, or route."""


class ConflictError(MeetStreamError):
    """409 - deduplication conflict: same ``deduplication_key``, different meeting."""


class RateLimitError(MeetStreamError):
    """429 - rate limited. ``retry_after`` is in seconds when the API supplied it."""

    def __init__(self, message: str, *, retry_after: Optional[float] = None, **kwargs: Any) -> None:
        super().__init__(message, **kwargs)
        self.retry_after = retry_after


class ServerError(MeetStreamError):
    """5xx - transient server error. Safe to retry with backoff."""


class NotReadyError(MeetStreamError):
    """The resource exists but is not ready yet (HTTP 202).

    This is **not** a failure. It is normal for transcripts and per-participant
    streams while a bot is still in the meeting or media is still processing.

    One trap: a bot that used a streaming-only transcription provider returns
    202 *forever*, because no post-call transcript will ever exist. Always cap
    your polling. The ``wait_for_*`` helpers do this for you.
    """


def error_for_status(
    status: int,
    message: str,
    *,
    body: Any = None,
    request_id: Optional[str] = None,
    retry_after: Optional[float] = None,
) -> MeetStreamError:
    """Map an HTTP status onto the right error class."""
    kwargs = {"status": status, "body": body, "request_id": request_id}
    if status == 202:
        return NotReadyError(message, **kwargs)
    if status == 400:
        return BadRequestError(message, **kwargs)
    if status == 401:
        return AuthenticationError(message, **kwargs)
    if status == 403:
        return PermissionError(message, **kwargs)
    if status == 404:
        return NotFoundError(message, **kwargs)
    if status == 409:
        return ConflictError(message, **kwargs)
    if status == 429:
        return RateLimitError(message, retry_after=retry_after, **kwargs)
    if status >= 500:
        return ServerError(message, **kwargs)
    return MeetStreamError(message, **kwargs)
