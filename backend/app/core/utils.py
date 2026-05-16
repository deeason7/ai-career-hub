"""Shared utility functions."""

import re

# Matches control characters except \t (0x09) and \n (0x0A).
_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def sanitize_text(text: str) -> str:
    """Strip HTML tags, null bytes, control characters, and collapse whitespace.

    Applied to all user-supplied free-text fields (job descriptions, commands)
    before they are stored in the database or passed to an LLM prompt.
    """
    text = re.sub(r"<[^>]+>", " ", text)
    text = _CONTROL_CHARS.sub("", text)
    return re.sub(r"\s+", " ", text).strip()
