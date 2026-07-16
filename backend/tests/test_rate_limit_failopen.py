"""The limiter must fail open — a dead Redis store cannot take login down with it."""

import importlib

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.core import limiter as limiter_module


def _reload_with(monkeypatch, **env):
    for key, value in env.items():
        if value is None:
            monkeypatch.delenv(key, raising=False)
        else:
            monkeypatch.setenv(key, value)
    return importlib.reload(limiter_module)


def _mini_app(mod):
    app = FastAPI()
    app.state.limiter = mod.limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    @app.get("/ping")
    @mod.rate_limit("3/minute")
    async def ping(request: Request):
        return {"ok": True}

    return app


def test_dead_redis_store_never_500s(monkeypatch):
    # Port 9 refuses instantly — a dead store, not a slow one. This is the AWS
    # outage shape: Redis container down, every rate-limited route raising.
    try:
        mod = _reload_with(
            monkeypatch,
            TESTING="false",
            REDIS_HOST="127.0.0.1",
            REDIS_PORT="9",
            REDIS_PASSWORD=None,
            REDIS_SSL=None,
        )
        client = TestClient(_mini_app(mod))
        codes = [client.get("/ping").status_code for _ in range(5)]
        assert 500 not in codes
        assert codes[:3] == [200, 200, 200]
        # The in-memory fallback keeps enforcing the limit during the outage.
        assert 429 in codes[3:]
    finally:
        _reload_with(monkeypatch, TESTING="true")


def test_no_redis_configured_still_limits_in_memory(monkeypatch):
    try:
        mod = _reload_with(
            monkeypatch,
            TESTING="false",
            REDIS_HOST=None,
            REDIS_PASSWORD=None,
            REDIS_SSL=None,
        )
        client = TestClient(_mini_app(mod))
        codes = [client.get("/ping").status_code for _ in range(4)]
        assert codes == [200, 200, 200, 429]
    finally:
        _reload_with(monkeypatch, TESTING="true")
