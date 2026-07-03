"""URL assembly for the Redis clients: DB overrides, TLS scheme, password quoting."""

from app.core import security
from app.services import task_state


def test_task_url_defaults_to_db_2(monkeypatch):
    monkeypatch.setenv("REDIS_HOST", "cache.local")
    monkeypatch.delenv("REDIS_PASSWORD", raising=False)
    monkeypatch.delenv("REDIS_SSL", raising=False)
    monkeypatch.delenv("REDIS_DB_TASKS", raising=False)

    assert task_state._redis_url() == "redis://cache.local:6379/2"


def test_task_url_honours_single_db_override(monkeypatch):
    monkeypatch.setenv("REDIS_HOST", "x.upstash.io")
    monkeypatch.setenv("REDIS_PASSWORD", "tok")
    monkeypatch.setenv("REDIS_SSL", "true")
    monkeypatch.setenv("REDIS_DB_TASKS", "0")

    assert task_state._redis_url() == "rediss://:tok@x.upstash.io:6379/0"


def test_task_url_quotes_special_password(monkeypatch):
    monkeypatch.setenv("REDIS_HOST", "cache.local")
    monkeypatch.setenv("REDIS_PASSWORD", "p@ss/w:rd%1")
    monkeypatch.delenv("REDIS_SSL", raising=False)
    monkeypatch.delenv("REDIS_DB_TASKS", raising=False)

    url = task_state._redis_url()

    assert "p%40ss%2Fw%3Ard%251" in url
    assert url.endswith("@cache.local:6379/2")


def _capture_denylist_url(monkeypatch):
    captured = {}

    def fake_from_url(url, **kwargs):
        captured["url"] = url
        return object()

    monkeypatch.setattr(security, "_redis", None)
    monkeypatch.setattr(security.aioredis, "from_url", fake_from_url)
    assert security._get_redis() is not None
    return captured["url"]


def test_denylist_url_defaults_to_db_1(monkeypatch):
    monkeypatch.setenv("REDIS_HOST", "cache.local")
    monkeypatch.setenv("REDIS_PASSWORD", "tok")
    monkeypatch.delenv("REDIS_SSL", raising=False)
    monkeypatch.delenv("REDIS_DB_DENYLIST", raising=False)

    assert _capture_denylist_url(monkeypatch) == "redis://:tok@cache.local:6379/1"


def test_denylist_url_honours_single_db_override(monkeypatch):
    monkeypatch.setenv("REDIS_HOST", "x.upstash.io")
    monkeypatch.setenv("REDIS_PASSWORD", "tok")
    monkeypatch.setenv("REDIS_SSL", "true")
    monkeypatch.setenv("REDIS_DB_DENYLIST", "0")

    assert _capture_denylist_url(monkeypatch) == "rediss://:tok@x.upstash.io:6379/0"
