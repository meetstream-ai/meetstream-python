"""Official MeetStream SDK for Python.

Send AI meeting bots into Zoom, Google Meet and Microsoft Teams. Record,
transcribe, summarize and stream meetings, and run MIA voice agents.

    from meetstream import MeetStream, segment_speaker, segment_text

    meetstream = MeetStream()  # reads MEETSTREAM_API_KEY

    bot = meetstream.bots.create({
        "meeting_link": "https://meet.google.com/abc-defg-hij",
        "bot_name": "Notetaker",
        "recording_config": {
            "transcript": {"provider": {"deepgram": {"model": "nova-3", "language": "en"}}}
        },
    })

    for segment in meetstream.transcripts.wait_for(bot["transcript_id"]):
        print(segment_speaker(segment), segment_text(segment))

Docs: https://docs.meetstream.ai
"""
from __future__ import annotations

from typing import Any, Dict, Optional

import httpx

from ._client import (
    DEFAULT_BASE_URL,
    AsyncMeetStreamTransport,
    MeetStreamTransport,
)
from ._errors import (
    AuthenticationError,
    BadRequestError,
    BalanceUnavailableError,
    ConflictError,
    ConnectionError,
    MeetStreamError,
    NotFoundError,
    NotReadyError,
    PermissionError,
    RateLimitError,
    ServerError,
    TimeoutError,
    TranscriptFailedError,
    is_inbuilt_keys_unavailable,
)
from .resources import (
    AsyncBilling,
    AsyncBots,
    AsyncCalendar,
    AsyncGoogleLogins,
    AsyncMeetingDirectConnect,
    AsyncMia,
    AsyncStorage,
    AsyncTeamsLogins,
    AsyncTranscripts,
    AsyncZoom,
    Billing,
    Bots,
    Calendar,
    GoogleLogins,
    MeetingDirectConnect,
    Mia,
    Storage,
    TeamsLogins,
    Transcripts,
    Zoom,
)
from .transcript import segment_speaker, segment_start, segment_text
from .webhooks import (
    PARTICIPANT_HAND_EVENTS,
    describe_stop,
    hand_event,
    is_terminal,
    parse_webhook,
    stop_reason,
    verify_webhook_signature,
)

__version__ = "1.4.4"

__all__ = [
    "MeetStream", "AsyncMeetStream", "__version__", "DEFAULT_BASE_URL",
    "MeetStreamError", "ConnectionError", "TimeoutError", "BadRequestError",
    "AuthenticationError", "PermissionError", "NotFoundError", "ConflictError",
    "RateLimitError", "ServerError", "NotReadyError", "TranscriptFailedError", "BalanceUnavailableError",
    "is_inbuilt_keys_unavailable",
    "verify_webhook_signature", "parse_webhook", "is_terminal", "stop_reason", "describe_stop",
    "PARTICIPANT_HAND_EVENTS", "hand_event",
    "segment_speaker", "segment_text", "segment_start",
]


class MeetStream:
    """Synchronous MeetStream client.

    Usable as a context manager, which closes the underlying HTTP connection
    pool on exit.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        *,
        base_url: Optional[str] = None,
        timeout: float = 60.0,
        max_retries: int = 2,
        default_headers: Optional[Dict[str, str]] = None,
        http_client: Optional[httpx.Client] = None,
    ) -> None:
        self.http = MeetStreamTransport(
            api_key,
            base_url=base_url,
            timeout=timeout,
            max_retries=max_retries,
            default_headers=default_headers,
            http_client=http_client,
        )
        self.bots = Bots(self.http)
        self.transcripts = Transcripts(self.http)
        self.calendar = Calendar(self.http)
        self.mia = Mia(self.http)
        self.google_logins = GoogleLogins(self.http)
        self.teams_logins = TeamsLogins(self.http)
        self.zoom = Zoom(self.http)
        self.storage = Storage(self.http)
        self.meeting_direct_connect = MeetingDirectConnect(self.http)
        self.billing = Billing(self.http)

    def close(self) -> None:
        self.http.close()

    def __enter__(self) -> "MeetStream":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()


class AsyncMeetStream:
    """Asynchronous MeetStream client. Same surface, awaited."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        *,
        base_url: Optional[str] = None,
        timeout: float = 60.0,
        max_retries: int = 2,
        default_headers: Optional[Dict[str, str]] = None,
        http_client: Optional[httpx.AsyncClient] = None,
    ) -> None:
        self.http = AsyncMeetStreamTransport(
            api_key,
            base_url=base_url,
            timeout=timeout,
            max_retries=max_retries,
            default_headers=default_headers,
            http_client=http_client,
        )
        self.bots = AsyncBots(self.http)
        self.transcripts = AsyncTranscripts(self.http)
        self.calendar = AsyncCalendar(self.http)
        self.mia = AsyncMia(self.http)
        self.google_logins = AsyncGoogleLogins(self.http)
        self.teams_logins = AsyncTeamsLogins(self.http)
        self.zoom = AsyncZoom(self.http)
        self.storage = AsyncStorage(self.http)
        self.meeting_direct_connect = AsyncMeetingDirectConnect(self.http)
        self.billing = AsyncBilling(self.http)

    async def aclose(self) -> None:
        await self.http.aclose()

    async def __aenter__(self) -> "AsyncMeetStream":
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self.aclose()
