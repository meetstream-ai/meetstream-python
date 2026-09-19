"""Bot lifecycle, media, meeting data and live interaction."""
from __future__ import annotations

import asyncio
import time
from typing import Any, Dict, Optional
from urllib.parse import quote

from .._errors import NotReadyError


def _p(bot_id: str) -> str:
    return quote(str(bot_id), safe="")


class Bots:
    """Synchronous bot operations."""

    def __init__(self, transport: Any) -> None:
        self._t = transport

    def create(self, params: Dict[str, Any], *, idempotency_key: Optional[str] = None, **kw: Any) -> Any:
        """Send a bot into a meeting.

        Pass ``idempotency_key`` and a retry returns the original bot (HTTP 507)
        rather than creating a duplicate. Generate that UUID once, outside your
        retry loop, and persist it with the job.

        Signed-in joins: pass ``"google_meet"`` or ``"teams"`` as
        ``{"login_required": True, "google_login_domain" | "teams_login_domain": ...,
        "sign_in_email"?: ..., "strict_email"?: bool}``. A signed-in Teams bot
        uses the Microsoft account's own name and picture, so ``bot_name`` and
        ``bot_image_url`` are not applied, and each Teams account runs one bot
        at a time.
        """
        return self._t.post("/bots/create_bot", params, idempotency_key=idempotency_key, **kw)

    def list(self, **kw: Any) -> Any:
        return self._t.get("/bots", **kw)

    def status(self, bot_id: str, **kw: Any) -> Any:
        return self._t.get(f"/bots/{_p(bot_id)}/status", **kw)

    def detail(self, bot_id: str, **kw: Any) -> Any:
        """Full record, including ``transcript_id``."""
        return self._t.get(f"/bots/{_p(bot_id)}/detail", **kw)

    def summary(self, bot_id: str, **kw: Any) -> Any:
        """AI-generated summary of the meeting."""
        return self._t.get(f"/bots/{_p(bot_id)}/summary", **kw)

    def remove(self, bot_id: str, **kw: Any) -> Any:
        """Make the bot leave. Recording and transcript are **kept**.

        This really is a GET on the MeetStream API, not a POST or DELETE.
        """
        return self._t.get(f"/bots/{_p(bot_id)}/remove_bot", **kw)

    def delete_data(self, bot_id: str, **kw: Any) -> Any:
        """Permanently erase audio, video and transcripts. Irreversible."""
        return self._t.delete(f"/bots/{_p(bot_id)}/delete", **kw)

    # media -----------------------------------------------------------------
    def audio(self, bot_id: str, **kw: Any) -> Any:
        return self._t.get(f"/bots/{_p(bot_id)}/get_audio", **kw)

    def video(self, bot_id: str, **kw: Any) -> Any:
        return self._t.get(f"/bots/{_p(bot_id)}/get_video", **kw)

    def audio_streams(self, bot_id: str, **kw: Any) -> Any:
        """Per-participant audio. Requires ``audio_separate_streams`` at creation."""
        return self._t.get(f"/bots/{_p(bot_id)}/get_audio_streams", **kw)

    def recording_streams(self, bot_id: str, **kw: Any) -> Any:
        """Per-participant video. Requires ``video_separate_streams`` at creation."""
        return self._t.get(f"/bots/{_p(bot_id)}/get_recording_streams", **kw)

    def screenshots(self, bot_id: str, **kw: Any) -> Any:
        return self._t.get(f"/bots/{_p(bot_id)}/get_screenshots", **kw)

    # meeting data ----------------------------------------------------------
    def participants(self, bot_id: str, **kw: Any) -> Any:
        return self._t.get(f"/bots/{_p(bot_id)}/get_participants", **kw)

    def chats(self, bot_id: str, **kw: Any) -> Any:
        return self._t.get(f"/bots/{_p(bot_id)}/get_chats", **kw)

    def speaker_timeline(self, bot_id: str, **kw: Any) -> Any:
        return self._t.get(f"/bots/{_p(bot_id)}/get_speaker_timeline", **kw)

    # interaction -----------------------------------------------------------
    def send_message(self, bot_id: str, message: str, **kw: Any) -> Any:
        return self._t.post(f"/bots/{_p(bot_id)}/send_message", {"message": message}, **kw)

    def send_image(self, bot_id: str, img_url: str, display_duration: Optional[int] = None, **kw: Any) -> Any:
        """``img_url`` must be a publicly reachable URL, not base64."""
        body: Dict[str, Any] = {"img_url": img_url}
        if display_duration is not None:
            body["display_duration"] = display_duration
        return self._t.post(f"/bots/{_p(bot_id)}/send_image", body, **kw)

    def pause_recording(self, bot_id: str, **kw: Any) -> Any:
        """Stop recording without leaving. Useful for privacy windows."""
        return self._t.post(f"/bots/{_p(bot_id)}/pause_recording", {}, **kw)

    def resume_recording(self, bot_id: str, **kw: Any) -> Any:
        return self._t.post(f"/bots/{_p(bot_id)}/resume_recording", {}, **kw)

    # helpers ---------------------------------------------------------------
    def _poll(self, fn: Any, timeout: float, interval: float) -> Any:
        deadline = time.monotonic() + timeout
        while True:
            try:
                return fn()
            except NotReadyError:
                if time.monotonic() + interval > deadline:
                    raise NotReadyError(
                        "Still not ready after {}s. If this bot used a streaming-only "
                        "transcription provider there is no post-call artifact and this "
                        "will never become ready.".format(int(timeout)),
                        status=202,
                    ) from None
                time.sleep(interval)

    def wait_for_audio(self, bot_id: str, *, timeout: float = 600.0, interval: float = 5.0, **kw: Any) -> Any:
        """Wait for processed audio. Always bounded."""
        return self._poll(lambda: self.audio(bot_id, **kw), timeout, interval)

    def wait_for_video(self, bot_id: str, *, timeout: float = 600.0, interval: float = 5.0, **kw: Any) -> Any:
        """Wait for processed video. Always bounded."""
        return self._poll(lambda: self.video(bot_id, **kw), timeout, interval)


class AsyncBots(Bots):
    """Asynchronous bot operations. Same surface, awaited."""

    async def create(self, params: Dict[str, Any], *, idempotency_key: Optional[str] = None, **kw: Any) -> Any:
        return await self._t.post("/bots/create_bot", params, idempotency_key=idempotency_key, **kw)

    async def list(self, **kw: Any) -> Any:
        return await self._t.get("/bots", **kw)

    async def status(self, bot_id: str, **kw: Any) -> Any:
        return await self._t.get(f"/bots/{_p(bot_id)}/status", **kw)

    async def detail(self, bot_id: str, **kw: Any) -> Any:
        return await self._t.get(f"/bots/{_p(bot_id)}/detail", **kw)

    async def summary(self, bot_id: str, **kw: Any) -> Any:
        return await self._t.get(f"/bots/{_p(bot_id)}/summary", **kw)

    async def remove(self, bot_id: str, **kw: Any) -> Any:
        return await self._t.get(f"/bots/{_p(bot_id)}/remove_bot", **kw)

    async def delete_data(self, bot_id: str, **kw: Any) -> Any:
        return await self._t.delete(f"/bots/{_p(bot_id)}/delete", **kw)

    async def audio(self, bot_id: str, **kw: Any) -> Any:
        return await self._t.get(f"/bots/{_p(bot_id)}/get_audio", **kw)

    async def video(self, bot_id: str, **kw: Any) -> Any:
        return await self._t.get(f"/bots/{_p(bot_id)}/get_video", **kw)

    async def audio_streams(self, bot_id: str, **kw: Any) -> Any:
        return await self._t.get(f"/bots/{_p(bot_id)}/get_audio_streams", **kw)

    async def recording_streams(self, bot_id: str, **kw: Any) -> Any:
        return await self._t.get(f"/bots/{_p(bot_id)}/get_recording_streams", **kw)

    async def screenshots(self, bot_id: str, **kw: Any) -> Any:
        return await self._t.get(f"/bots/{_p(bot_id)}/get_screenshots", **kw)

    async def participants(self, bot_id: str, **kw: Any) -> Any:
        return await self._t.get(f"/bots/{_p(bot_id)}/get_participants", **kw)

    async def chats(self, bot_id: str, **kw: Any) -> Any:
        return await self._t.get(f"/bots/{_p(bot_id)}/get_chats", **kw)

    async def speaker_timeline(self, bot_id: str, **kw: Any) -> Any:
        return await self._t.get(f"/bots/{_p(bot_id)}/get_speaker_timeline", **kw)

    async def send_message(self, bot_id: str, message: str, **kw: Any) -> Any:
        return await self._t.post(f"/bots/{_p(bot_id)}/send_message", {"message": message}, **kw)

    async def send_image(self, bot_id: str, img_url: str, display_duration: Optional[int] = None, **kw: Any) -> Any:
        body: Dict[str, Any] = {"img_url": img_url}
        if display_duration is not None:
            body["display_duration"] = display_duration
        return await self._t.post(f"/bots/{_p(bot_id)}/send_image", body, **kw)

    async def pause_recording(self, bot_id: str, **kw: Any) -> Any:
        return await self._t.post(f"/bots/{_p(bot_id)}/pause_recording", {}, **kw)

    async def resume_recording(self, bot_id: str, **kw: Any) -> Any:
        return await self._t.post(f"/bots/{_p(bot_id)}/resume_recording", {}, **kw)

    async def _apoll(self, fn: Any, timeout: float, interval: float) -> Any:
        deadline = time.monotonic() + timeout
        while True:
            try:
                return await fn()
            except NotReadyError:
                if time.monotonic() + interval > deadline:
                    raise NotReadyError(
                        "Still not ready after {}s. If this bot used a streaming-only "
                        "transcription provider there is no post-call artifact and this "
                        "will never become ready.".format(int(timeout)),
                        status=202,
                    ) from None
                await asyncio.sleep(interval)

    async def wait_for_audio(self, bot_id: str, *, timeout: float = 600.0, interval: float = 5.0, **kw: Any) -> Any:
        return await self._apoll(lambda: self.audio(bot_id, **kw), timeout, interval)

    async def wait_for_video(self, bot_id: str, *, timeout: float = 600.0, interval: float = 5.0, **kw: Any) -> Any:
        return await self._apoll(lambda: self.video(bot_id, **kw), timeout, interval)
