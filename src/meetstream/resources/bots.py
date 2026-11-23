"""Bot lifecycle, media, meeting data and live interaction."""
from __future__ import annotations

import asyncio
import time
import warnings
from typing import Any, Dict, Optional
from urllib.parse import quote

from .._errors import NotReadyError

_SUMMARY_GONE = (
    "bots.summary() is deprecated: the MeetStream API has no summary endpoint and the call "
    "returns 404. Fetch the transcript (transcripts.get_by_bot(bot_id), transcripts.get() with the "
    "transcript_id from bots.detail(), or GET /bots/{bot_id}/get_transcript) and summarize it "
    "with your own LLM."
)


def _p(bot_id: str) -> str:
    return quote(str(bot_id), safe="")


def _with_params(kw: Dict[str, Any], **values: Any) -> Dict[str, Any]:
    """Merge the given query params (skipping ``None``) into the request kwargs."""
    extra = {k: v for k, v in values.items() if v is not None}
    if not extra:
        return kw
    params = dict(kw.pop("params", None) or {})
    params.update(extra)
    return {**kw, "params": params}


def _command_body(command: str, params: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    body = dict(params or {})
    body["command"] = command
    return body


def _update_mia_body(params: Dict[str, Any], wait_for_ack: Optional[bool]) -> Dict[str, Any]:
    body = dict(params)
    if wait_for_ack is not None:
        body["wait_for_ack"] = wait_for_ack
    return body


def _timeline_url(result: Any) -> Optional[str]:
    if isinstance(result, dict) and isinstance(result.get("speaker_timeline_url"), str):
        return result["speaker_timeline_url"]
    return None


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

        Recording defaults: ``video_required`` defaults to ``False``, so the bot
        records audio only (transcripts, diarization and speaker timelines all
        work from audio alone). Send ``True`` only when video was asked for, and
        then set ``{"recording_config": {"video_layout": "speaker_view"}}``: the
        API defaults that to ``"grid_view"``, and speaker view follows the
        active speaker. On Google Meet and Teams, ``"speaker_view_default"`` and
        ``"grid_view_default"`` record with the platform's own default view.
        Leave ``video_separate_streams`` unset unless per-participant video was
        explicitly requested; on Google Meet and Teams it needs
        ``video_required: True``.

        Zoom bots join through your Zoom app (Meeting SDK) with an OBF token
        (``"zoom": {"obf_url": ...}``, on behalf of a user who is in the
        meeting) or a ZAK token (``"zoom": {"zak_url": ...}``, a signed-in
        bot). Setup: https://docs.meetstream.ai/guides/app-integrations/zoom-marketplace-app-setup
        and https://docs.meetstream.ai/guides/app-integrations/zoom-authenticated-bots.

        Other options: ``storage_id`` picks one of the storage destinations
        saved in the dashboard; ``bot_camera_stream`` (``{"websocket_url":
        ...}``) publishes your own video through the bot's camera. See
        :class:`meetstream.types.CreateBotParams` for the field list.

        Prepaid accounts have a per-minute and per-hour create limit. Over it
        the API answers 429 with ``Retry-After``; the SDK retries a short wait
        and raises :class:`RateLimitError` (with ``retry_after``) for a long one.
        """
        return self._t.post("/bots/create_bot", params, idempotency_key=idempotency_key, **kw)

    def list(self, **kw: Any) -> Any:
        """List bots. Filter with ``params={"status": ..., "from": ..., "to": ..., "platform": ...}``.

        For very large accounts ``summary`` can carry ``"partial": True``.
        """
        return self._t.get("/bots", **kw)

    def get(self, bot_id: str, **kw: Any) -> Any:
        """The bot's record. Same response as :meth:`detail`."""
        return self._t.get(f"/bots/{_p(bot_id)}", **kw)

    def status(self, bot_id: str, **kw: Any) -> Any:
        return self._t.get(f"/bots/{_p(bot_id)}/status", **kw)

    def detail(self, bot_id: str, **kw: Any) -> Any:
        """Full record, including ``transcript_id``."""
        return self._t.get(f"/bots/{_p(bot_id)}/detail", **kw)

    def summary(self, bot_id: str, **kw: Any) -> Any:
        """Deprecated: the API has no summary endpoint, so this returns 404.

        ``GET /bots/{bot_id}/summary`` was removed. Fetch the transcript with
        ``transcripts.get_by_bot(bot_id)`` (or ``transcripts.get()`` with the
        ``transcript_id`` from ``bots.detail()``, or
        ``GET /bots/{bot_id}/get_transcript``) and summarize it with your own
        LLM. Kept so existing code still runs; emits ``DeprecationWarning``.
        """
        warnings.warn(_SUMMARY_GONE, DeprecationWarning, stacklevel=2)
        return self._t.get(f"/bots/{_p(bot_id)}/summary", **kw)

    def remove(self, bot_id: str, **kw: Any) -> Any:
        """Make the bot leave. Recording and transcript are **kept**.

        This really is a GET on the MeetStream API, not a POST or DELETE.
        Returns the stop state: HTTP 202 (stop still in progress) is returned
        as a value, not raised. Follow it with :meth:`stop_status`.
        """
        try:
            return self._t.get(f"/bots/{_p(bot_id)}/remove_bot", **kw)
        except NotReadyError as exc:
            return exc.body

    def stop_status(self, bot_id: str, **kw: Any) -> Any:
        """Progress of a stop request, without stopping the bot again."""
        try:
            return self._t.get(f"/bots/{_p(bot_id)}/stop_status", **kw)
        except NotReadyError as exc:
            return exc.body

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

    def screenshots(
        self,
        bot_id: str,
        *,
        limit: Optional[int] = None,
        recorded_at_after: Optional[str] = None,
        recorded_at_before: Optional[str] = None,
        continuation_token: Optional[str] = None,
        action: Optional[str] = None,
        meta: Optional[str] = None,
        **kw: Any,
    ) -> Any:
        """Screenshots, newest first, each with a one-hour download URL.

        Page with ``continuation_token`` (``next_continuation_token`` from the
        last page), sending back that page's ``meta``. Use ``action="prev"``
        with ``prev_continuation_token`` to page backwards.
        """
        return self._t.get(
            f"/bots/{_p(bot_id)}/screenshots",
            **_with_params(
                kw, limit=limit, recorded_at_after=recorded_at_after, recorded_at_before=recorded_at_before,
                continuation_token=continuation_token, action=action, meta=meta,
            ),
        )

    def screenshot(self, bot_id: str, screenshot_id: str, **kw: Any) -> Any:
        """One screenshot by id, with a fresh one-hour download URL."""
        return self._t.get(f"/bots/{_p(bot_id)}/screenshots/{_p(screenshot_id)}", **kw)

    # meeting data ----------------------------------------------------------
    def participants(self, bot_id: str, **kw: Any) -> Any:
        return self._t.get(f"/bots/{_p(bot_id)}/get_participants", **kw)

    def chats(self, bot_id: str, **kw: Any) -> Any:
        return self._t.get(f"/bots/{_p(bot_id)}/get_chats", **kw)

    def speaker_timeline(self, bot_id: str, *, download: bool = False, **kw: Any) -> Any:
        """The speaker timeline.

        A large timeline comes back as a download link instead of inline:
        ``{"bot_id", "speaker_timeline_url", "size_bytes", "truncated"}`` (see
        :class:`meetstream.types.SpeakerTimelineDownload`). The link is valid
        for one hour and needs no API key. Pass ``download=True`` to fetch it
        for you, so you always get the timeline itself.
        """
        result = self._t.get(f"/bots/{_p(bot_id)}/get_speaker_timeline", **kw)
        url = _timeline_url(result)
        if download and url:
            return self._t.fetch_presigned(url, timeout=kw.get("timeout"))
        return result

    # interaction -----------------------------------------------------------
    def send_message(self, bot_id: str, message: str, **kw: Any) -> Any:
        return self._t.post(f"/bots/{_p(bot_id)}/send_message", {"message": message}, **kw)

    def send_image(self, bot_id: str, img_url: str, display_duration: Optional[int] = None, **kw: Any) -> Any:
        """``img_url`` must be a public https URL, not base64.

        The bot downloads it, and every redirect hop must resolve to a public
        address or the image is refused.
        """
        body: Dict[str, Any] = {"img_url": img_url}
        if display_duration is not None:
            body["display_duration"] = display_duration
        return self._t.post(f"/bots/{_p(bot_id)}/send_image", body, **kw)

    def pause_recording(self, bot_id: str, **kw: Any) -> Any:
        """Stop recording without leaving. Useful for privacy windows."""
        return self._t.post(f"/bots/{_p(bot_id)}/pause_recording", {}, **kw)

    def resume_recording(self, bot_id: str, **kw: Any) -> Any:
        return self._t.post(f"/bots/{_p(bot_id)}/resume_recording", {}, **kw)

    def send_command(self, bot_id: str, command: str, params: Optional[Dict[str, Any]] = None, **kw: Any) -> Any:
        """Send a command to a bot in the meeting, e.g. ``"raise_hand"`` or ``"lower_hand"``.

        ``params`` holds the command's other body fields, if it has any. The
        bot must be in the meeting (409 otherwise). WhatsApp and Zoom Meeting
        Direct Connect sessions answer 400 with ``error.code``
        ``unsupported_on_whatsapp`` / ``unsupported_on_zoom_rtms``.
        """
        return self._t.post(f"/bots/{_p(bot_id)}/send_command", _command_body(command, params), **kw)

    def raise_hand(self, bot_id: str, **kw: Any) -> Any:
        """Raise the bot's hand. Google Meet, Zoom and Teams.

        Safe to repeat. The response's ``hand_raised`` is the state the bot saw
        in the meeting after it acted.
        """
        return self.send_command(bot_id, "raise_hand", **kw)

    def lower_hand(self, bot_id: str, **kw: Any) -> Any:
        """Lower the bot's hand. Same rules as :meth:`raise_hand`."""
        return self.send_command(bot_id, "lower_hand", **kw)

    def update_mia(
        self, bot_id: str, params: Dict[str, Any], *, wait_for_ack: Optional[bool] = None, **kw: Any
    ) -> Any:
        """Update a running MIA agent mid-call. The saved agent config is not changed.

        ``params``: any of ``agent_config_params``, ``system_prompt``,
        ``wake_word_enabled``, ``wake_words``. With ``wait_for_ack=True`` the
        response carries the agent's result: ``status`` is ``applied``,
        ``partially_applied``, ``failed`` or ``accepted``, plus ``applied``,
        ``errors`` and ``ack_timeout`` when the bot returns them.
        """
        return self._t.post(f"/bots/{_p(bot_id)}/update_mia", _update_mia_body(params, wait_for_ack), **kw)

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

    async def get(self, bot_id: str, **kw: Any) -> Any:
        return await self._t.get(f"/bots/{_p(bot_id)}", **kw)

    async def status(self, bot_id: str, **kw: Any) -> Any:
        return await self._t.get(f"/bots/{_p(bot_id)}/status", **kw)

    async def detail(self, bot_id: str, **kw: Any) -> Any:
        return await self._t.get(f"/bots/{_p(bot_id)}/detail", **kw)

    async def summary(self, bot_id: str, **kw: Any) -> Any:
        """Deprecated: the API has no summary endpoint, so this returns 404.

        ``GET /bots/{bot_id}/summary`` was removed. Fetch the transcript with
        ``transcripts.get_by_bot(bot_id)`` (or ``transcripts.get()`` with the
        ``transcript_id`` from ``bots.detail()``, or
        ``GET /bots/{bot_id}/get_transcript``) and summarize it with your own
        LLM. Kept so existing code still runs; emits ``DeprecationWarning``.
        """
        warnings.warn(_SUMMARY_GONE, DeprecationWarning, stacklevel=2)
        return await self._t.get(f"/bots/{_p(bot_id)}/summary", **kw)

    async def remove(self, bot_id: str, **kw: Any) -> Any:
        try:
            return await self._t.get(f"/bots/{_p(bot_id)}/remove_bot", **kw)
        except NotReadyError as exc:
            return exc.body

    async def stop_status(self, bot_id: str, **kw: Any) -> Any:
        try:
            return await self._t.get(f"/bots/{_p(bot_id)}/stop_status", **kw)
        except NotReadyError as exc:
            return exc.body

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

    async def screenshots(
        self,
        bot_id: str,
        *,
        limit: Optional[int] = None,
        recorded_at_after: Optional[str] = None,
        recorded_at_before: Optional[str] = None,
        continuation_token: Optional[str] = None,
        action: Optional[str] = None,
        meta: Optional[str] = None,
        **kw: Any,
    ) -> Any:
        return await self._t.get(
            f"/bots/{_p(bot_id)}/screenshots",
            **_with_params(
                kw, limit=limit, recorded_at_after=recorded_at_after, recorded_at_before=recorded_at_before,
                continuation_token=continuation_token, action=action, meta=meta,
            ),
        )

    async def screenshot(self, bot_id: str, screenshot_id: str, **kw: Any) -> Any:
        return await self._t.get(f"/bots/{_p(bot_id)}/screenshots/{_p(screenshot_id)}", **kw)

    async def participants(self, bot_id: str, **kw: Any) -> Any:
        return await self._t.get(f"/bots/{_p(bot_id)}/get_participants", **kw)

    async def chats(self, bot_id: str, **kw: Any) -> Any:
        return await self._t.get(f"/bots/{_p(bot_id)}/get_chats", **kw)

    async def speaker_timeline(self, bot_id: str, *, download: bool = False, **kw: Any) -> Any:
        result = await self._t.get(f"/bots/{_p(bot_id)}/get_speaker_timeline", **kw)
        url = _timeline_url(result)
        if download and url:
            return await self._t.fetch_presigned(url, timeout=kw.get("timeout"))
        return result

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

    async def send_command(
        self, bot_id: str, command: str, params: Optional[Dict[str, Any]] = None, **kw: Any
    ) -> Any:
        return await self._t.post(f"/bots/{_p(bot_id)}/send_command", _command_body(command, params), **kw)

    async def raise_hand(self, bot_id: str, **kw: Any) -> Any:
        return await self.send_command(bot_id, "raise_hand", **kw)

    async def lower_hand(self, bot_id: str, **kw: Any) -> Any:
        return await self.send_command(bot_id, "lower_hand", **kw)

    async def update_mia(
        self, bot_id: str, params: Dict[str, Any], *, wait_for_ack: Optional[bool] = None, **kw: Any
    ) -> Any:
        return await self._t.post(f"/bots/{_p(bot_id)}/update_mia", _update_mia_body(params, wait_for_ack), **kw)

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
