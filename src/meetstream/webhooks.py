"""Webhook signature verification and lifecycle helpers."""
from __future__ import annotations

import hashlib
import hmac
import json
from typing import Any, Dict, Union

__all__ = ["verify_webhook_signature", "parse_webhook", "is_terminal", "stop_reason", "describe_stop"]


def verify_webhook_signature(payload: Union[str, bytes], signature: str, secret: str) -> bool:
    """Verify a MeetStream webhook signature.

    Pass the **raw request body**, exactly as received. Re-serializing a parsed
    dict changes key order and whitespace, and the signature will never match.

    In Flask that means ``request.get_data()``, not ``request.json``. In
    FastAPI, ``await request.body()``.

    Accepts both a bare hex digest and a ``sha256=`` prefixed form.
    """
    if not signature or not secret:
        return False
    body = payload.encode("utf-8") if isinstance(payload, str) else payload
    expected = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    candidate = signature[7:] if signature.startswith("sha256=") else signature
    return hmac.compare_digest(expected, candidate.strip())


def parse_webhook(payload: Union[str, bytes], signature: str, secret: str) -> Dict[str, Any]:
    """Verify and parse in one step.

    Raises :class:`ValueError` when the signature does not match, so a forged
    payload can never reach your handler.
    """
    if not verify_webhook_signature(payload, signature, secret):
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
