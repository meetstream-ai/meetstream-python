"""Errors raised by the MeetStream SDK.

MeetStream error responses carry a ``message`` field; it becomes
``error.message`` and the raw body is kept on ``error.body``. Older responses
used an ``error`` key or a bare JSON string instead, and both are still read.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

__all__ = [
    "MeetStreamError", "ConnectionError", "TimeoutError", "BadRequestError",
    "AuthenticationError", "PermissionError", "NotFoundError", "ConflictError",
    "RateLimitError", "ServerError", "NotReadyError", "TranscriptFailedError",
    "BalanceUnavailableError", "is_inbuilt_keys_unavailable", "error_for_status",
]

import re as _re


class MeetStreamError(Exception):
    """Base class for everything this SDK raises."""

    def __init__(
        self,
        message: str,
        *,
        status: Optional[int] = None,
        body: Any = None,
        request_id: Optional[str] = None,
        retry_after: Optional[float] = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.status = status
        self.body = body
        self.request_id = request_id
        #: Seconds from the ``Retry-After`` header (or the body's ``retry_after``), when sent.
        self.retry_after = retry_after

    @property
    def code(self) -> Optional[str]:
        """The machine-readable ``code`` from the error body, when the API sent one.

        For example ``unsupported_on_whatsapp`` or ``unsupported_on_zoom_rtms``.
        """
        if isinstance(self.body, dict):
            value = self.body.get("code")
            if isinstance(value, str) and value:
                return value
        return None

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
    """409 - the request conflicts with the current state.

    Examples: the same ``deduplication_key`` with a different meeting, or a
    command sent to a bot that is not in the meeting. When ``retry_after`` is
    set, another request with the same idempotency or deduplication key is
    still being saved: retry with the **same** key after that many seconds.
    """


class RateLimitError(MeetStreamError):
    """429 - rate limited. ``retry_after`` is in seconds when the API supplied it.

    Prepaid accounts are limited to a number of bot creates per minute and per
    hour; the body then also carries ``limit`` and ``window`` (``"minute"`` or
    ``"hour"``). No bot is created by a 429.
    """


class TranscriptFailedError(MeetStreamError):
    """422 from ``get_transcript`` - the transcript **failed** and will not become ready.

    A final answer, not a server error: do not retry the same read. Read
    ``reason`` (for example the provider rejected the API key, or a provider
    usage limit was reached), fix the cause, then call
    ``transcripts.transcribe_bot_audio()`` for a new transcript.

    Docs: https://docs.meetstream.ai/errors#failed-transcript-422
    """

    def __init__(self, message: str, **kwargs: Any) -> None:
        super().__init__(message, **kwargs)
        body = self.body if isinstance(self.body, dict) else {}
        status = body.get("transcript_status")
        #: The transcript status the API reported, normally ``"Failed"``.
        self.transcript_status: str = status if isinstance(status, str) else "Failed"
        tid = body.get("transcript_id")
        #: The id of the failed transcript, when the API sent it.
        self.transcript_id: Optional[str] = tid if isinstance(tid, str) else None
        #: Why it failed, without the ``Transcript processing failed:`` prefix.
        self.reason: str = _re.sub(r"^Transcript processing failed:?\s*", "", message, flags=_re.I) or message


class BalanceUnavailableError(NotFoundError):
    """404 from ``billing.balance()``: the balance endpoint is not on for this account yet.

    Read the balance on https://app.meetstream.ai/billing. Do not retry.
    """

    billing_url = "https://app.meetstream.ai/billing"


def is_inbuilt_keys_unavailable(error: Any) -> bool:
    """True when the API refused MeetStream's inbuilt keys because they are not on for the account yet.

    The message then reads, for example, ``MeetStream-managed keys are not
    available for model. Use your own key.`` Use your own provider key for that
    section (``key_source: "user"``, or leave it out) and continue. Do not
    retry the same request.
    """
    message = error.message if isinstance(error, MeetStreamError) else str(error or "")
    return bool(_re.search(r"MeetStream-managed keys are not available", message, flags=_re.I))


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
    kwargs: Dict[str, Any] = {"status": status, "body": body, "request_id": request_id, "retry_after": retry_after}
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
    if status == 422 and isinstance(body, dict) and isinstance(body.get("transcript_status"), str):
        return TranscriptFailedError(message, **kwargs)
    if status == 429:
        return RateLimitError(message, **kwargs)
    if status >= 500:
        return ServerError(message, **kwargs)
    return MeetStreamError(message, **kwargs)
