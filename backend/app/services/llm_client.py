"""Structured LLM client backed by instructor.

Wraps Groq (production) or Ollama (local dev) with instructor's Pydantic
validation and automatic retry logic.
"""

import logging
from typing import TypeVar

from pydantic import BaseModel, ValidationError

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

# Lazy-initialised singleton — avoids import-time side effects.
_client = None
_active_model: str | None = None


def _get_client():
    """Build an instructor-patched client (singleton).

    Groq path: instructor.from_groq() — used when GROQ_API_KEY is set.
    Ollama path: instructor wraps an OpenAI client pointed at Ollama's
    local endpoint. No OpenAI API key required — Ollama ignores it.
    """
    global _client, _active_model  # noqa: PLW0603
    if _client is not None:
        return _client, _active_model

    import instructor

    from app.core.config import settings

    if settings.USE_GROQ:
        import groq

        raw_client = groq.Groq(api_key=settings.GROQ_API_KEY, timeout=60.0)
        _client = instructor.from_groq(raw_client, mode=instructor.Mode.JSON)
        _active_model = settings.GROQ_LLM_MODEL
        logger.info("Instructor client: Groq (%s)", _active_model)
    else:
        from openai import OpenAI

        # Ollama's OpenAI-compatible endpoint — the api_key is a dummy
        # value; Ollama doesn't validate it. The openai package is free.
        raw_client = OpenAI(
            base_url=f"{settings.OLLAMA_BASE_URL}/v1",
            api_key="ollama",
        )
        _client = instructor.from_openai(raw_client, mode=instructor.Mode.JSON)
        _active_model = settings.OLLAMA_LLM_MODEL
        logger.info("Instructor client: Ollama (%s)", _active_model)

    return _client, _active_model


def call_structured(
    *,
    response_model: type[T],
    system_prompt: str,
    user_prompt: str,
    model: str | None = None,
    temperature: float = 0.3,
    max_retries: int = 3,
) -> T:
    """Send a prompt to the active LLM and return a validated Pydantic model.

    Instructor retries on validation failure, feeding the error back to the
    model so it can self-correct. Raises ValidationError after max_retries.
    """
    from instructor.core.exceptions import InstructorRetryException

    client, default_model = _get_client()
    model_id = model or default_model

    logger.debug(
        "call_structured: model=%s, response_model=%s, retries=%d",
        model_id,
        response_model.__name__,
        max_retries,
    )

    try:
        result = client.chat.completions.create(
            model=model_id,
            response_model=response_model,
            max_retries=max_retries,
            temperature=temperature,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
    except InstructorRetryException as exc:
        logger.warning(
            "Structured output failed after %d retries for %s",
            max_retries,
            response_model.__name__,
        )
        inner = exc.__cause__
        if isinstance(inner, ValidationError):
            raise inner from exc
        raise ValidationError.from_exception_data(
            title=response_model.__name__,
            line_errors=[],
        ) from exc

    logger.debug("call_structured: success — %s", response_model.__name__)
    return result


def reset_client() -> None:
    """Reset the singleton client. Used by tests to inject different backends."""
    global _client, _active_model  # noqa: PLW0603
    _client = None
    _active_model = None
