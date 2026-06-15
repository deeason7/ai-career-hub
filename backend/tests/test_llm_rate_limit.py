"""Unit tests for call_structured's 429 backoff — no live model involved."""

import httpx
import pytest
from groq import RateLimitError
from pydantic import BaseModel

from app.services import llm_client
from app.services.llm_client import LLMRateLimitedError, call_structured


class _Out(BaseModel):
    text: str


def _rate_limit_error(retry_after: str | None = None) -> RateLimitError:
    headers = {"retry-after": retry_after} if retry_after else {}
    response = httpx.Response(
        429,
        headers=headers,
        request=httpx.Request("POST", "https://api.test/v1/chat/completions"),
    )
    return RateLimitError("rate limited", response=response, body=None)


class _FlakyClient:
    """Raises 429 a set number of times, then returns a parsed model."""

    def __init__(self, failures: int, retry_after: str | None = None):
        self.failures = failures
        self.retry_after = retry_after
        self.calls = 0
        # Mimic the client.chat.completions.create attribute chain.
        self.chat = self
        self.completions = self

    def create(self, **kwargs):
        self.calls += 1
        if self.calls <= self.failures:
            raise _rate_limit_error(self.retry_after)
        return _Out(text="ok")


@pytest.fixture
def sleeps(monkeypatch):
    """Record backoff waits instead of actually sleeping."""
    delays: list[float] = []
    monkeypatch.setattr(llm_client.time, "sleep", delays.append)
    return delays


def _use_fake_client(monkeypatch, fake: _FlakyClient) -> None:
    monkeypatch.setattr(llm_client, "_get_client", lambda: (fake, "test-model"))


def _call(**kwargs) -> _Out:
    return call_structured(
        response_model=_Out,
        system_prompt="system",
        user_prompt="user",
        **kwargs,
    )


def test_backs_off_then_succeeds(monkeypatch, sleeps):
    fake = _FlakyClient(failures=2)
    _use_fake_client(monkeypatch, fake)

    result = _call()

    assert result.text == "ok"
    assert fake.calls == 3
    # Exponential: base 2s, doubled per retry.
    assert sleeps == [2.0, 4.0]


def test_raises_once_budget_is_spent(monkeypatch, sleeps):
    fake = _FlakyClient(failures=100)
    _use_fake_client(monkeypatch, fake)

    with pytest.raises(LLMRateLimitedError):
        _call()

    assert fake.calls == llm_client._RATE_LIMIT_TRIES
    assert len(sleeps) == llm_client._RATE_LIMIT_TRIES - 1


def test_honors_retry_after_header(monkeypatch, sleeps):
    fake = _FlakyClient(failures=1, retry_after="11")
    _use_fake_client(monkeypatch, fake)

    _call()

    assert sleeps == [11.0]


def test_caps_retry_after_header(monkeypatch, sleeps):
    fake = _FlakyClient(failures=1, retry_after="300")
    _use_fake_client(monkeypatch, fake)

    _call()

    assert sleeps == [llm_client._RATE_LIMIT_MAX_DELAY]


def test_on_busy_hears_each_wait(monkeypatch, sleeps):
    fake = _FlakyClient(failures=2)
    _use_fake_client(monkeypatch, fake)
    waits: list[float] = []

    result = _call(on_busy=waits.append)

    assert result.text == "ok"
    assert waits == [2.0, 4.0]


def test_on_busy_errors_do_not_kill_the_call(monkeypatch, sleeps):
    fake = _FlakyClient(failures=1)
    _use_fake_client(monkeypatch, fake)

    def broken_callback(_delay: float) -> None:
        raise RuntimeError("progress writer down")

    result = _call(on_busy=broken_callback)

    assert result.text == "ok"
