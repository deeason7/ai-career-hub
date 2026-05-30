"""Shared utility functions."""

import re

# Matches control characters except \t (0x09) and \n (0x0A).
_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")

# Fenced code blocks and role-injection tokens that adversarial JD text may embed.
_INJECTION_TOKENS = re.compile(
    r"```.*?```"
    r"|\nHuman:|\nAssistant:|\nSystem:"
    r"|</s>|<\|im_start\|>|<\|im_end\|>"
    r"|\[INST\]|\[/INST\]|<<SYS>>|<</SYS>>",
    re.DOTALL | re.IGNORECASE,
)


def sanitize_text(text: str) -> str:
    """Strip HTML tags, null bytes, control characters, and collapse whitespace."""
    text = re.sub(r"<[^>]+>", " ", text)
    text = _CONTROL_CHARS.sub("", text)
    return re.sub(r"\s+", " ", text).strip()


def _sanitize_jd_for_prompt(text: str) -> str:
    """Strip prompt-injection patterns before JD text enters any LLM call."""
    return _INJECTION_TOKENS.sub(" ", text).strip()
