"""Zoom Meeting Direct Connect: record a Zoom meeting with no bot in it.

Zoom streams the meeting to MeetStream through your own Zoom app (Zoom's
Realtime Media Streams). A session is a normal bot with ``platform:
"ZoomRTMS"``, so every ``bots.*`` and ``transcripts.*`` read works with its
``bot_id``. Sessions are receive-only: commands, chat, images, raise hand and
MIA answer 400 with code ``unsupported_on_zoom_rtms``.

See the "Zoom Meeting Direct Connect" guide at https://docs.meetstream.ai.
"""
from __future__ import annotations

from typing import Any, Dict
from urllib.parse import quote


def _p(value: str) -> str:
    return quote(str(value), safe="")


class MeetingDirectConnect:
    """Synchronous Meeting Direct Connect operations."""

    def __init__(self, transport: Any) -> None:
        self._t = transport

    def create(self, params: Dict[str, Any], **kw: Any) -> Any:
        """Start a session from Zoom's ``meeting.rtms_started`` webhook.

        ``params`` needs ``zoom_rtms``: ``meeting_uuid``, ``rtms_stream_id``,
        ``server_urls`` and your ``signature``. Your Zoom client secret stays
        on your server.
        """
        return self._t.post("/meeting_direct_connect", params, **kw)

    def get(self, bot_id: str, **kw: Any) -> Any:
        return self._t.get(f"/meeting_direct_connect/{_p(bot_id)}", **kw)

    def leave(self, bot_id: str, **kw: Any) -> Any:
        """Stop recording the session. Post-call processing then runs as usual."""
        return self._t.post(f"/meeting_direct_connect/{_p(bot_id)}/leave", {}, **kw)


class AsyncMeetingDirectConnect(MeetingDirectConnect):
    """Asynchronous Meeting Direct Connect operations."""

    async def create(self, params: Dict[str, Any], **kw: Any) -> Any:
        return await self._t.post("/meeting_direct_connect", params, **kw)

    async def get(self, bot_id: str, **kw: Any) -> Any:
        return await self._t.get(f"/meeting_direct_connect/{_p(bot_id)}", **kw)

    async def leave(self, bot_id: str, **kw: Any) -> Any:
        return await self._t.post(f"/meeting_direct_connect/{_p(bot_id)}/leave", {}, **kw)
