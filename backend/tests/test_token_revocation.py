"""Token revocation fails open when Redis is unavailable or erroring."""

from redis.exceptions import ConnectionError as RedisConnectionError

from app.core import security


class _FakeRedis:
    """Minimal async Redis stand-in whose ops can be told to raise."""

    def __init__(self, *, exists_result: int = 0, raises: bool = False):
        self._exists_result = exists_result
        self._raises = raises
        self.setex_calls: list[tuple] = []

    async def exists(self, key):
        if self._raises:
            raise RedisConnectionError("redis down")
        return self._exists_result

    async def setex(self, key, ttl, value):
        if self._raises:
            raise RedisConnectionError("redis down")
        self.setex_calls.append((key, ttl, value))


async def test_is_token_revoked_returns_false_when_redis_absent(monkeypatch):
    monkeypatch.setattr(security, "_get_redis", lambda: None)
    assert await security.is_token_revoked("jti-1") is False


async def test_is_token_revoked_fails_open_on_redis_error(monkeypatch):
    # A Redis hiccup must not propagate — it would 500 every authenticated request.
    monkeypatch.setattr(security, "_get_redis", lambda: _FakeRedis(raises=True))
    assert await security.is_token_revoked("jti-2") is False


async def test_is_token_revoked_true_when_present(monkeypatch):
    monkeypatch.setattr(security, "_get_redis", lambda: _FakeRedis(exists_result=1))
    assert await security.is_token_revoked("jti-3") is True


async def test_revoke_token_swallows_redis_error(monkeypatch):
    # Logout should succeed even if the denylist write fails; token expires on its own.
    monkeypatch.setattr(security, "_get_redis", lambda: _FakeRedis(raises=True))
    await security.revoke_token("jti-4", ttl_seconds=60)
