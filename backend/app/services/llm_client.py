"""Structured LLM client backed by instructor.

Wraps Groq (production) or Ollama (local dev) with instructor's Pydantic
validation and automatic retry logic.
"""

import logging
import time
from collections.abc import Callable
from typing import TypeVar

from pydantic import BaseModel, ValidationError

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

# Lazy-initialised singleton — avoids import-time side effects.
_client = None
_active_model: str | None = None

# Rate-limit backoff. Groq's free tier caps tokens per minute, so a 429 storm
# usually clears within the minute: waits double from the base (or follow the
# server's Retry-After), both capped, before the call is declared busy.
_RATE_LIMIT_TRIES = 4
_RATE_LIMIT_BASE_DELAY = 2.0
_RATE_LIMIT_MAX_DELAY = 20.0


class LLMRateLimitedError(Exception):
    """The model was still rate-limited after the backoff budget was spent."""


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


def _rate_limit_errors() -> tuple[type[Exception], ...]:
    """The provider 429 classes — imported lazily like the SDKs themselves."""
    from groq import RateLimitError as GroqRateLimit
    from openai import RateLimitError as OpenAIRateLimit

    return (GroqRateLimit, OpenAIRateLimit)


def _retry_after_seconds(exc: Exception) -> float | None:
    """Pull the server's Retry-After hint off a 429, if it sent one."""
    response = getattr(exc, "response", None)
    if response is None:
        return None
    try:
        return float(response.headers.get("retry-after"))
    except (TypeError, ValueError):
        return None


def _wait_out_rate_limit(
    attempt: int, exc: Exception, on_busy: Callable[[float], None] | None
) -> None:
    """Sleep through one 429, or raise LLMRateLimitedError when the budget is spent."""
    if attempt >= _RATE_LIMIT_TRIES - 1:
        logger.error("model still rate-limited after %d attempts — giving up", _RATE_LIMIT_TRIES)
        raise LLMRateLimitedError("LLM rate limit persisted through backoff") from exc
    delay = _RATE_LIMIT_BASE_DELAY * (2**attempt)
    retry_after = _retry_after_seconds(exc)
    if retry_after is not None:
        delay = max(delay, retry_after)
    delay = min(delay, _RATE_LIMIT_MAX_DELAY)
    logger.warning(
        "model rate-limited (attempt %d/%d) — waiting %.0fs",
        attempt + 1,
        _RATE_LIMIT_TRIES,
        delay,
    )
    if on_busy is not None:
        try:
            on_busy(delay)
        except Exception:
            logger.debug("on_busy callback failed", exc_info=True)
    time.sleep(delay)


def call_structured(
    *,
    response_model: type[T],
    system_prompt: str,
    user_prompt: str,
    model: str | None = None,
    temperature: float = 0.3,
    max_retries: int = 3,
    on_busy: Callable[[float], None] | None = None,
) -> T:
    """Send a prompt to the active LLM and return a validated Pydantic model.

    Instructor retries on validation failure, feeding the error back to the
    model so it can self-correct. Raises ValidationError after max_retries.
    Provider rate limits (429) are waited out with capped exponential backoff
    — on_busy hears each wait so callers can surface an honest status — and
    raise LLMRateLimitedError once the backoff budget is spent.
    """
    try:
        from instructor.core.exceptions import InstructorRetryException
    except ImportError:  # instructor relocated this across the >=1.3 range
        from instructor.exceptions import InstructorRetryException

    client, default_model = _get_client()
    model_id = model or default_model
    rate_limited = _rate_limit_errors()

    logger.debug(
        "call_structured: model=%s, response_model=%s, retries=%d",
        model_id,
        response_model.__name__,
        max_retries,
    )

    for attempt in range(_RATE_LIMIT_TRIES):
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
            break
        except rate_limited as exc:
            _wait_out_rate_limit(attempt, exc, on_busy)
        except InstructorRetryException as exc:
            # A 429 can surface wrapped if it fired inside instructor's retry.
            if isinstance(exc.__cause__, rate_limited):
                _wait_out_rate_limit(attempt, exc.__cause__, on_busy)
                continue
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


def check_ollama_model() -> None:
    """Warn at startup when the Ollama fallback can't actually serve.

    A missing model otherwise stays invisible until the first fallback call
    fails mid-request with a confusing 404.
    """
    import httpx

    from app.core.config import settings

    try:
        resp = httpx.get(f"{settings.OLLAMA_BASE_URL}/api/tags", timeout=5.0)
        resp.raise_for_status()
        available = {m.get("name", "") for m in resp.json().get("models", [])}
    except Exception as exc:
        logger.warning(
            "Ollama unreachable at %s (%s) — the fallback LLM path is unavailable",
            settings.OLLAMA_BASE_URL,
            type(exc).__name__,
        )
        return

    wanted = settings.OLLAMA_LLM_MODEL
    if wanted not in available and f"{wanted}:latest" not in available:
        logger.warning(
            "Ollama model %s is not pulled (available: %s) — run `ollama pull %s` "
            "or fallback generations will fail",
            wanted,
            ", ".join(sorted(available)) or "none",
            wanted,
        )


def reset_client() -> None:
    """Reset the singleton client. Used by tests to inject different backends."""
    global _client, _active_model  # noqa: PLW0603
    _client = None
    _active_model = None
