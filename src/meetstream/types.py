"""Optional type hints for request and response shapes.

Every method still takes and returns plain dicts, so nothing here is required.
Annotate your own dicts with these to get editor completion and type checking:

    from meetstream.types import CreateBotParams

    params: CreateBotParams = {
        "meeting_link": "https://zoom.us/j/123",
        "zoom": {"use_own_app": False},
    }
    meetstream.bots.create(params)

The ``TypedDict`` classes are ``total=False``: they list the fields this SDK
knows about, and the API may accept or return more. String values that come
from the API (statuses, reasons, event names) are not a closed set; treat an
unknown value as a normal case.
"""
from __future__ import annotations

from typing import Any, Dict, List, Literal, TypedDict, Union

__all__ = [
    "VideoLayout", "TranscriptionProvider", "RealtimeEvent", "BotStatus", "HandCommand",
    "ZoomOptions", "BotCameraStream", "AutomaticLeave", "SmallestOptions", "SmallestStreamingOptions",
    "TranscriptProvider", "TranscriptConfig", "RealtimeEndpoint", "RecordingConfig", "CreateBotParams",
    "SpeakerTimelineDownload", "HandCommandResponse", "UpdateMiaParams", "UpdateMiaResponse",
    "MiaModelConfig", "RateLimitBody",
]

VideoLayout = Literal["speaker_view", "grid_view", "speaker_view_default", "grid_view_default"]
"""``recording_config.video_layout``.

``speaker_view_default`` and ``grid_view_default`` record the meeting with the
platform's own default view and are Google Meet and Teams only; Zoom accepts
``speaker_view`` and ``grid_view``.
"""

TranscriptionProvider = Literal[
    "deepgram", "deepgram_streaming", "assemblyai", "assemblyai_streaming", "jigsawstack",
    "sarvam", "meetstream", "meeting_captions", "smallest", "smallest_streaming",
]
"""Keys of ``recording_config.transcript.provider``."""

RealtimeEvent = Union[
    Literal[
        "participant_events.join",
        "participant_events.leave",
        "participant_events.chat_message",
        "participant_events.raise_hand",
        "participant_events.lower_hand",
    ],
    str,
]
"""Values for ``recording_config.realtime_endpoints[].events``.

The hand events are opt-in per bot: they go only to realtime endpoints that
list them, never to workspace webhooks.
"""

BotStatus = Union[
    Literal[
        "Scheduled", "Joining", "InWaitingRoom", "InMeeting", "RecordingPermissionAllowed",
        "RecordingPermissionDenied", "Leaving", "Stopped", "Kicked", "NotAllowed", "Denied",
        "Failed", "Error", "MediaProcessing", "Done", "MediaExpired", "Cancelled",
    ],
    str,
]
"""A bot's ``status``. Not a closed set; compare case-insensitively."""

HandCommand = Literal["raise_hand", "lower_hand"]


class ZoomOptions(TypedDict, total=False):
    """``zoom`` on create_bot.

    ``use_own_app``: ``True`` joins with your connected Zoom app (and needs
    one); ``False`` joins with no Zoom app or credentials and cannot be
    combined with ``zak_url`` or ``obf_url``; omitted or ``None`` uses your app
    when one is connected and otherwise joins without one.
    """

    use_own_app: Union[bool, None]
    zak_url: str
    obf_url: str


class BotCameraStream(TypedDict, total=False):
    """``bot_camera_stream``: video (and optional audio) you publish through the bot's camera.

    Google Meet accepts ``ws://`` or ``wss://``; Teams and Zoom need ``wss://``.
    On Zoom it cannot be combined with ``agent_config_id``.
    """

    websocket_url: str


class AutomaticLeave(TypedDict, total=False):
    """``automatic_leave`` timeouts, in whole seconds."""

    waiting_room_timeout: int
    no_one_joined_timeout: int
    everyone_left_timeout: int
    voice_inactivity_timeout: int
    in_call_recording_timeout: int
    recording_permission_denied_timeout: int
    """Zoom only. 60 to 600, default 600."""
    bot_detection: Dict[str, Any]


class SmallestOptions(TypedDict, total=False):
    """Smallest AI post-call transcription. Needs your Smallest AI key saved in the dashboard."""

    model: Literal["pulse", "pulse-pro"]
    language: str
    diarize: bool
    keywords: Union[str, List[str]]
    redact_pii: bool
    redact_pci: bool
    emotion_detection: bool
    gender_detection: bool


class SmallestStreamingOptions(TypedDict, total=False):
    """Smallest AI live transcription. Needs your Smallest AI key saved in the dashboard."""

    model: Literal["pulse", "pulse-2"]
    language: str


class TranscriptProvider(TypedDict, total=False):
    """``recording_config.transcript.provider``: set exactly one key."""

    deepgram: Dict[str, Any]
    deepgram_streaming: Dict[str, Any]
    assemblyai: Dict[str, Any]
    assemblyai_streaming: Dict[str, Any]
    jigsawstack: Dict[str, Any]
    sarvam: Dict[str, Any]
    meetstream: Dict[str, Any]
    meeting_captions: Dict[str, Any]
    smallest: SmallestOptions
    smallest_streaming: SmallestStreamingOptions


class TranscriptConfig(TypedDict, total=False):
    provider: TranscriptProvider


class RealtimeEndpoint(TypedDict, total=False):
    type: str
    url: str
    events: List[RealtimeEvent]


class RecordingConfig(TypedDict, total=False):
    video_layout: VideoLayout
    video_quality: Literal["standard", "hd"]
    retention: Dict[str, Any]
    transcript: TranscriptConfig
    realtime_endpoints: List[RealtimeEndpoint]


class CreateBotParams(TypedDict, total=False):
    """Body of ``bots.create``. Only ``meeting_link`` is required."""

    meeting_link: str
    bot_name: str
    storage_id: str
    """A storage destination saved in the dashboard: 1-80 letters, numbers, ``_`` or ``-``."""
    audio_required: bool
    video_required: bool
    audio_mixed_mp3: bool
    audio_separate_mp3: bool
    audio_separate_streams: bool
    video_separate_streams: bool
    deduplication_key: str
    initial_audio: Dict[str, Any]
    agent_config_id: str
    agent_config_params: Dict[str, Any]
    zoom: ZoomOptions
    google_meet: Dict[str, Any]
    teams: Dict[str, Any]
    bot_message: str
    bot_image_url: str
    callback_url: str
    join_at: str
    custom_attributes: Dict[str, Any]
    socket_connection_url: Dict[str, Any]
    live_audio_required: Dict[str, Any]
    live_transcription_required: Dict[str, Any]
    bot_camera_stream: BotCameraStream
    automatic_leave: AutomaticLeave
    recording_config: RecordingConfig


class SpeakerTimelineDownload(TypedDict):
    """``get_speaker_timeline`` answer for a large timeline.

    ``speaker_timeline_url`` is a pre-signed download link, valid for one hour,
    that needs no API key. The file has the same format as the inline answer.
    """

    bot_id: str
    speaker_timeline_url: str
    size_bytes: int
    truncated: bool


class HandCommandResponse(TypedDict, total=False):
    status: str
    bot_id: str
    command: HandCommand
    hand_raised: bool
    """The hand state the bot read back from the meeting after it acted."""


class UpdateMiaParams(TypedDict, total=False):
    """Body of ``bots.update_mia``. Send at least one field."""

    agent_config_params: Dict[str, Any]
    system_prompt: str
    wake_word_enabled: bool
    wake_words: List[str]


class UpdateMiaResponse(TypedDict, total=False):
    """``status`` is ``applied``, ``partially_applied``, ``failed`` or ``accepted`` with ``wait_for_ack``."""

    status: str
    bot_id: str
    command: str
    applied: Any
    errors: Any
    ack_timeout: bool


class MiaModelConfig(TypedDict, total=False):
    """``model`` in a MIA agent config.

    With ``provider: "anthropic"`` (pipeline mode), save your Anthropic key in
    the dashboard. ``tool_choice`` must be ``auto`` or ``none``, and ``top_p``,
    ``frequency_penalty``, ``presence_penalty`` and ``logit_bias`` are rejected.
    """

    provider: Union[Literal["openai", "anthropic", "xai", "google"], str]
    model: str
    system_prompt: str
    first_message: str
    temperature: float
    reasoning_effort: Literal["none", "minimal", "low", "medium", "high", "xhigh", "max"]
    tool_choice: str
    max_tokens: int


class RateLimitBody(TypedDict, total=False):
    """Body of a 429 from create_bot. Also on ``RateLimitError.body``."""

    error: str
    message: str
    limit: int
    window: Literal["minute", "hour"]
    retry_after: int
