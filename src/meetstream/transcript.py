"""Read transcript segments from ``get_transcript``.

A segment names the speaker in ``participant.name`` and holds the text in a
``words`` list (``words[].text``)::

    {"participant": {"id": 100, "name": "Alice", "platform": "desktop"},
     "words": [{"text": "Hello everyone.",
                "start_timestamp": {"relative": 12.0, "absolute": ...},
                "end_timestamp": {"relative": 13.1, "absolute": ...}}],
     "language_code": "en"}

Some providers also send flat ``speaker`` and ``transcript`` fields. These
helpers read both shapes, so a transcript never "looks empty" because the
code read the wrong field.
"""
from __future__ import annotations

from typing import Any, Mapping, Optional

__all__ = ["segment_speaker", "segment_text", "segment_start"]


def segment_speaker(segment: Mapping[str, Any], default: str = "Unknown") -> str:
    """Speaker name: ``participant.name``, else the flat ``speaker`` field."""
    participant = segment.get("participant")
    if isinstance(participant, Mapping):
        name = participant.get("name")
        if isinstance(name, str) and name.strip():
            return name.strip()
    speaker = segment.get("speaker")
    if isinstance(speaker, str) and speaker.strip():
        return speaker.strip()
    return default


def segment_text(segment: Mapping[str, Any]) -> str:
    """Segment text: ``words[].text`` joined with spaces, else the flat ``transcript`` field."""
    words = segment.get("words")
    if isinstance(words, list):
        parts = []
        for word in words:
            if isinstance(word, Mapping):
                text = word.get("text")
                if text is None:
                    text = word.get("punctuated_word", word.get("word"))
                if isinstance(text, str) and text.strip():
                    parts.append(text.strip())
        if parts:
            return " ".join(parts)
    for key in ("transcript", "text"):
        value = segment.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def segment_start(segment: Mapping[str, Any]) -> Optional[float]:
    """Start in seconds from the meeting start, or ``None`` when the segment has none."""
    if isinstance(segment.get("start_time"), (int, float)):
        return float(segment["start_time"])
    words = segment.get("words")
    if isinstance(words, list) and words and isinstance(words[0], Mapping):
        stamp = words[0].get("start_timestamp")
        if isinstance(stamp, Mapping) and isinstance(stamp.get("relative"), (int, float)):
            return float(stamp["relative"])
    return None
