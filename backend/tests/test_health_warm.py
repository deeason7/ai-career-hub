"""Warm-probe response shape and the boot-time Redis reachability warning."""

from unittest.mock import AsyncMock, patch

import pytest_asyncio

from app import main as app_main


@pytest_asyncio.fixture(autouse=True)
async def _close_task_redis():
    """Close the lazily-created task-store client while the loop is still open."""
    # Left to the GC, the async client outlives the loop and spews
    # "Event loop is closed" at interpreter exit.
    yield
    from app.services import task_state

    if task_state._redis is not None:
        await task_state._redis.aclose()
        task_state._redis = None


async def test_warm_probe_reports_ok_dependencies(client):
    from app.services import embedding_service as es

    es.reset_client()

    # CI runs no Redis service, so stub a healthy client instead of leaning on a
    # live one — this test pins the probe's ok-shape, not real connectivity.
    healthy = AsyncMock()
    healthy.ping.return_value = True

    with patch("app.services.task_state._get_redis", return_value=healthy):
        res = await client.get("/health/warm")

    assert res.status_code == 200
    body = res.json()
    assert body["api"] == "ok"
    assert body["db"] == {"status": "ok", "detail": None}
    assert body["redis"] == {"status": "ok", "detail": None}
    assert body["vector"]["backend"] == "chroma"


async def test_warm_probe_carries_redis_failure_detail(client):
    broken = AsyncMock()
    broken.ping.side_effect = ConnectionError("connection reset by peer")

    with patch("app.services.task_state._get_redis", return_value=broken):
        res = await client.get("/health/warm")

    assert res.status_code == 200
    body = res.json()
    assert body["redis"]["status"] == "down"
    assert "ConnectionError" in body["redis"]["detail"]
    assert "connection reset by peer" in body["redis"]["detail"]


async def test_warm_probe_reports_disabled_when_unconfigured(client):
    with patch("app.services.task_state._get_redis", return_value=None):
        res = await client.get("/health/warm")

    assert res.json()["redis"] == {"status": "disabled", "detail": None}


def test_boot_probe_warns_when_redis_unreachable(monkeypatch, caplog):
    dead = "redis://127.0.0.1:1/0"
    monkeypatch.setattr("app.services.task_state._redis_url", lambda: dead)
    monkeypatch.setattr("app.core.security._redis_url", lambda: dead)

    with caplog.at_level("WARNING"):
        app_main._check_redis_reachable()

    assert "unreachable" in caplog.text
    assert "task state" in caplog.text
    assert "token deny-list" in caplog.text


def test_boot_probe_silent_when_unconfigured(monkeypatch, caplog):
    monkeypatch.setattr("app.services.task_state._redis_url", lambda: None)
    monkeypatch.setattr("app.core.security._redis_url", lambda: None)

    with caplog.at_level("WARNING"):
        app_main._check_redis_reachable()

    assert "unreachable" not in caplog.text
