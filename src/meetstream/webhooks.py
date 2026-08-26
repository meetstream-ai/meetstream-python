"""Webhook signature verification and lifecycle helpers."""
from __future__ import annotations

import hashlib
import hmac
import json
from typing import Any, Dict, Union

__all__ = ["verify_webhook_signature", "parse_webhook", "is_terminal", "describe_stop"]


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
    """True when this event ends the bot's meeting lifecycle.

    ``bot.stopped`` is the single terminal event and always carries
    ``status_code: 200``, whatever the reason - read ``bot_status`` to find out
    why. ``bot.error`` is deliberately not terminal: the bot keeps running.
    """
    return event.get("event") == "bot.stopped"


def describe_stop(event: Dict[str, Any]) -> str:
    """Human-readable explanation of why a bot stopped."""
    status = event.get("bot_status")
    if status == "Stopped":
        return "The bot left normally."
    if status == "NotAllowed":
        return "The bot sat in the waiting room until it timed out. Nobody admitted it."
    if status == "Denied":
        return "A host actively refused the bot. This is a human decision; do not auto-retry."
    if status == "Error":
        return "The bot session crashed. Create a fresh bot."
    return event.get("message") or "Bot stopped with status {}.".format(status or "unknown")
