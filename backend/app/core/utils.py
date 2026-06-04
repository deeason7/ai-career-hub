"""Shared utility functions."""

import re

# Matches control characters except \t (0x09) and \n (0x0A).
_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")

# Patterns adversarial JD text may embed to hijack the prompt. Replaced with a
# space before the text reaches any LLM call — defense-in-depth behind the
# "use only verified facts" system prompt, not a substitute for it.
_INJECTION_TOKENS = re.compile(
    r"```.*?```"  # fenced code blocks
    r"|(?m:^[ \t]*(?:human|assistant|system|user|ai)[ \t]*:)"  # role labels at any line start
    r"|</s>|<\|im_start\|>|<\|im_end\|>|<\|im_sep\|>"  # ChatML
    r"|<\|begin_of_text\|>|<\|eot_id\|>|<\|start_header_id\|>|<\|end_header_id\|>"  # Llama 3
    r"|\[INST\]|\[/INST\]|<<SYS>>|<</SYS>>"  # Llama 2 / Mistral
    r"|(?:ignore|disregard|forget)[ \t]+(?:all[ \t]+|the[ \t]+|any[ \t]+)?"
    r"(?:previous|prior|above|preceding|earlier)[ \t]+"
    r"(?:instructions?|prompts?|messages?|context)",  # override phrases
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
