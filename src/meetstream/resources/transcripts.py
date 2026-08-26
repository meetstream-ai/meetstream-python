"""Transcript retrieval and re-transcription."""
from __future__ import annotations

import asyncio
import time
from typing import Any, Dict, Optional
from urllib.parse import quote

from .._errors import NotReadyError

_STREAMING_HINT = (
    "Transcript {tid} was still not ready after {secs}s. If the bot used a streaming-only "
    "provider the transcript was delivered live and no post-call transcript exists; use "
    "transcribe_bot_audio() to generate one."
)


def _p(value: str) -> str:
    return quote(str(value), safe="")


class Transcripts:
    """Synchronous transcript operations."""

    def __init__(self, transport: Any) -> None:
        self._t = transport

    def get(self, transcript_id: str, *, raw: bool = False, **kw: Any) -> Any:
        """Fetch a transcript by **transcript_id**, not bot_id.

        Segments use a ``transcript`` field, not ``text``. Reading the wrong
        field is the usual reason a transcript "looks empty".

        Raises :class:`NotReadyError` on HTTP 202.
        """
        return self._t.get(f"/transcript/{_p(transcript_id)}/get_transcript", params={"raw": raw}, **kw)

    def list_for_bot(self, bot_id: str, **kw: Any) -> Any:
        return self._t.get(f"/bots/{_p(bot_id)}/transcriptions", **kw)

    def transcribe_bot_audio(self, bot_id: str, body: Optional[Dict[str, Any]] = None, **kw: Any) -> Any:
        """Re-transcribe a bot's stored audio.

        The escape hatch when a bot used a streaming-only provider: the live
        stream was the only record, and this produces a post-call transcript
        from the stored audio after the fact.
        """
        return self._t.post(f"/bots/{_p(bot_id)}/transcribe", body or {}, **kw)

    def wait_for(self, transcript_id: str, *, timeout: float = 900.0, interval: float = 5.0, **kw: Any) -> Any:
        """Wait for a transcript. Always bounded.

        Never unbounded on purpose: streaming-only providers return 202 forever
        because no post-call transcript will ever exist.
        """
        deadline = time.monotonic() + timeout
        while True:
            try:
                return self.get(transcript_id, **kw)
            except NotReadyError:
                if time.monotonic() + interval > deadline:
                    raise NotReadyError(
                        _STREAMING_HINT.format(tid=transcript_id, secs=int(timeout)), status=202
                    ) from None
                time.sleep(interval)


class AsyncTranscripts(Transcripts):
    """Asynchronous transcript operations."""

    async def get(self, transcript_id: str, *, raw: bool = False, **kw: Any) -> Any:
        return await self._t.get(f"/transcript/{_p(transcript_id)}/get_transcript", params={"raw": raw}, **kw)

    async def list_for_bot(self, bot_id: str, **kw: Any) -> Any:
        return await self._t.get(f"/bots/{_p(bot_id)}/transcriptions", **kw)

    async def transcribe_bot_audio(self, bot_id: str, body: Optional[Dict[str, Any]] = None, **kw: Any) -> Any:
        return await self._t.post(f"/bots/{_p(bot_id)}/transcribe", body or {}, **kw)

    async def wait_for(self, transcript_id: str, *, timeout: float = 900.0, interval: float = 5.0, **kw: Any) -> Any:
        deadline = time.monotonic() + timeout
        while True:
            try:
                return await self.get(transcript_id, **kw)
            except NotReadyError:
                if time.monotonic() + interval > deadline:
                    raise NotReadyError(
                        _STREAMING_HINT.format(tid=transcript_id, secs=int(timeout)), status=202
                    ) from None
                await asyncio.sleep(interval)
