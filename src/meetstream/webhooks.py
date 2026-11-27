"""Webhook signature verification and lifecycle helpers."""
from __future__ import annotations

import hashlib
import hmac
import json
import time
from datetime import datetime, timezone
from typing import Any, Dict, Mapping, Optional, Union, cast

__all__ = [
    "verify_webhook_signature", "parse_webhook", "is_terminal", "stop_reason", "describe_stop",
    "PARTICIPANT_HAND_EVENTS", "hand_event", "is_final_segment",
    "BOT_ID_HEADER", "AGENT_ID_HEADER", "parse_custom_function_call",
]

#: Header on every MIA custom function call: the bot that made the call.
BOT_ID_HEADER = "X-Bot-ID"
#: Header on a MIA custom function call when the agent config is known.
AGENT_ID_HEADER = "X-Agent-ID"

#: Realtime participant events for a raised or lowered hand. Opt-in per bot:
#: list them in ``recording_config.realtime_endpoints[].events``. They are
#: never sent to workspace webhooks.
PARTICIPANT_HAND_EVENTS = ("participant_events.raise_hand", "participant_events.lower_hand")


def _parse_iso_timestamp(value: str) -> Optional[float]:
    """Seconds since the epoch for an ISO 8601 string, or ``None``.

    A trailing ``Z`` is read as UTC (``datetime.fromisoformat`` accepts it only
    from Python 3.11). A value without an offset is read as UTC.
    """
    text = value.strip()
    if text.endswith(("Z", "z")):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.timestamp()


def _signed_timestamp_within_tolerance(
    body: bytes, header_timestamp: Optional[str], tolerance_seconds: float, now: Optional[float]
) -> bool:
    """Replay check after the signature verified.

    Reads ``timestamp`` from the signed body (the HMAC covers the body, not the
    ``X-MeetStream-Timestamp`` header). The header, when sent, must match it.
    """
    try:
        parsed = json.loads(body.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return False
    signed = parsed.get("timestamp") if isinstance(parsed, dict) else None
    if not isinstance(signed, str):
        return False
    sent = _parse_iso_timestamp(signed)
    if sent is None:
        return False
    if header_timestamp is not None:
        header = _parse_iso_timestamp(header_timestamp) if isinstance(header_timestamp, str) else None
        if header is None or header != sent:
            return False
    current = time.time() if now is None else now
    return abs(current - sent) <= tolerance_seconds


def verify_webhook_signature(
    payload: Union[str, bytes],
    signature: str,
    secret: str,
    *,
    timestamp: Optional[str] = None,
    tolerance_seconds: Optional[float] = None,
    now: Optional[float] = None,
) -> bool:
    """Verify a MeetStream webhook signature.

    Only **workspace webhook endpoints** are signed (``X-MeetStream-Signature``
    and ``X-MeetStream-Timestamp``). Per-bot ``callback_url`` deliveries and
    live transcript POSTs are never signed: protect those with a secret token
    in the URL instead (see the README).

    Pass the **raw request body**, exactly as received. Re-serializing a parsed
    dict changes key order and whitespace, and the signature will never match.

    In Flask that means ``request.get_data()``, not ``request.json``. In
    FastAPI, ``await request.body()``.

    Accepts both a bare hex digest and a ``sha256=`` prefixed form.

    Optional replay window: set ``tolerance_seconds``, and pass the
    ``X-MeetStream-Timestamp`` header (an ISO 8601 UTC string such as
    ``2026-11-19T14:30:00Z``) as ``timestamp``. The window is checked against
    the ``timestamp`` field of the signed body, because the HMAC covers the
    body and not the header. The delivery is rejected when the body's
    timestamp is missing, cannot be parsed, or is more than that many seconds
    from ``now`` (seconds since the epoch; default the current time), or when
    the header is passed and does not match it. Off by default.
    """
    if not signature or not secret:
        return False
    body = payload.encode("utf-8") if isinstance(payload, str) else payload
    expected = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    candidate = signature[7:] if signature.startswith("sha256=") else signature
    if not hmac.compare_digest(expected, candidate.strip()):
        return False
    if tolerance_seconds is not None:
        return _signed_timestamp_within_tolerance(body, timestamp, tolerance_seconds, now)
    return True


def parse_webhook(
    payload: Union[str, bytes],
    signature: str,
    secret: str,
    *,
    timestamp: Optional[str] = None,
    tolerance_seconds: Optional[float] = None,
    now: Optional[float] = None,
) -> Dict[str, Any]:
    """Verify and parse in one step.

    Raises :class:`ValueError` when the signature does not match (or, with
    ``tolerance_seconds``, when the timestamp is outside the window), so a
    forged payload can never reach your handler.
    """
    if not verify_webhook_signature(
        payload, signature, secret, timestamp=timestamp, tolerance_seconds=tolerance_seconds, now=now
    ):
        raise ValueError("Webhook signature verification failed")
    body = payload if isinstance(payload, str) else payload.decode("utf-8")
    return json.loads(body)


def is_terminal(event: Dict[str, Any]) -> bool:
    """True when this event ends the bot's time in the meeting.

    Every ending arrives once as ``event: "bot.stopped"``, whatever the reason;
    :func:`stop_reason` tells you why. Post-call processing continues
    afterwards and ``bot.done`` is the final event. ``bot.error`` is
    deliberately not terminal: the bot keeps running.
    """
    return event.get("event") == "bot.stopped"


def stop_reason(event: Dict[str, Any]) -> str:
    """The specific reason a bot stopped.

    One of ``bot.stopped``, ``bot.kicked``, ``bot.notallowed``, ``bot.denied``
    or ``bot.failed``. Reads ``bot_event`` and falls back to ``bot_status``
    (case-insensitively) for payloads without it. ``bot_status`` alone cannot
    tell a kick from a clean exit: both are ``Stopped``.
    """
    reason = event.get("bot_event")
    if isinstance(reason, str) and reason:
        return reason
    status = str(event.get("bot_status") or "").lower()
    if status == "notallowed":
        return "bot.notallowed"
    if status == "denied":
        return "bot.denied"
    if status in ("error", "failed"):
        return "bot.failed"
    return "bot.stopped"


def describe_stop(event: Dict[str, Any]) -> str:
    """Human-readable explanation of why a bot stopped."""
    reason = stop_reason(event)
    if reason == "bot.stopped":
        return "The bot left normally."
    if reason == "bot.kicked":
        return "A participant removed the bot from the meeting."
    if reason == "bot.notallowed":
        return "The bot sat in the waiting room until it timed out. Nobody admitted it."
    if reason == "bot.denied":
        return "A host actively refused the bot. This is a human decision; do not auto-retry."
    if reason == "bot.failed":
        return "The bot session crashed. Create a fresh bot."
    return event.get("message") or "Bot stopped ({}).".format(reason)


def hand_event(event: Dict[str, Any]) -> Optional[str]:
    """``"raise_hand"`` or ``"lower_hand"`` for a participant hand event, else ``None``.

    Only changes are reported, never the bot's own hand. A participant who
    leaves with a hand up gets no ``lower_hand``, so clear their state on
    ``participant_events.leave`` too. The payload is shaped like
    ``participant_events.join``.
    """
    name = event.get("event")
    if name in PARTICIPANT_HAND_EVENTS:
        return str(name).split(".", 1)[1]
    return None


def is_final_segment(payload: Mapping[str, Any]) -> bool:
    """True when a live transcript POST is final text you can keep.

    - ``sentence`` mode: always true (only finals are sent).
    - ``word_level`` mode: always true (every word is final).
    - ``raw`` mode (the default when ``transcription_mode`` is absent): true
      when ``is_final`` or ``end_of_turn`` is ``True``; false for interim
      results.
    """
    mode = payload.get("transcription_mode") or "raw"
    if mode in ("sentence", "word_level"):
        return True
    return payload.get("is_final") is True or payload.get("end_of_turn") is True


def _read_header(headers: Optional[Mapping[str, Any]], name: str) -> Optional[str]:
    if not headers:
        return None
    wanted = name.lower()
    for key, value in headers.items():
        if str(key).lower() == wanted:
            if isinstance(value, (list, tuple)):
                value = value[0] if value else None
            return str(value) if value else None
    return None


def parse_custom_function_call(
    body: Union[str, bytes, Mapping[str, Any]],
    headers: Optional[Mapping[str, Any]] = None,
    *,
    payload_args_only: bool = False,
) -> Dict[str, Any]:
    """Read a MIA custom function call in your tool endpoint.

    Returns ``{"name", "bot_id", "agent_id", "args"}``, plus ``"bot"`` (the
    envelope's ``bot`` block) in envelope mode when the body has one.

    You state the body shape; it is never guessed from the content:

    - envelope (default):
      ``{"name", "bot": {"bot_id", "dynamic_vars", "agent_id"?, "speaker"?}, "args"}``.
    - ``payload_args_only=True``, for a function configured with
      ``payload_args_only``: the whole body is ``args``; ``name`` is ``None``
      and there is no ``bot``. Arguments come from the model, so they are
      never read as an envelope, even when they look like one.

    ``bot_id`` comes from the ``X-Bot-ID`` header first, and from
    ``bot.bot_id`` only when the header is missing and the mode is envelope
    (``agent_id`` likewise with ``X-Agent-ID``). ``headers`` is any mapping
    (Flask ``request.headers``, Starlette ``request.headers`` or a plain
    dict); lookup is case-insensitive.

    **Every field, ``X-Bot-ID`` included, is unauthenticated** unless your
    endpoint checks its own secret: put a token in the function's ``headers``
    and compare it before you trust the call.
    """
    if isinstance(body, bytes):
        body = body.decode("utf-8")
    parsed: Any = json.loads(body or "{}") if isinstance(body, str) else body
    obj: Dict[str, Any] = dict(parsed) if isinstance(parsed, Mapping) else {}
    header_bot_id = _read_header(headers, BOT_ID_HEADER)
    header_agent_id = _read_header(headers, AGENT_ID_HEADER)

    if payload_args_only:
        return {"name": None, "bot_id": header_bot_id, "agent_id": header_agent_id, "args": obj}

    name = obj.get("name")
    bot = obj.get("bot")
    args = obj.get("args")
    body_bot = cast(Mapping[str, Any], bot) if isinstance(bot, Mapping) else {}
    body_bot_id = body_bot.get("bot_id")
    body_agent_id = body_bot.get("agent_id")
    result: Dict[str, Any] = {
        "name": name if isinstance(name, str) else None,
        "bot_id": header_bot_id or (body_bot_id if isinstance(body_bot_id, str) else None),
        "agent_id": header_agent_id or (body_agent_id if isinstance(body_agent_id, str) else None),
        "args": dict(args) if isinstance(args, Mapping) else {},
    }
    if isinstance(bot, Mapping):
        result["bot"] = dict(bot)
    return result
