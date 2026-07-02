"""Central rate-limiter instance shared across all routers.

Uses Redis-backed storage in live environments so that rate counts survive
container restarts and are shared across replicas. Falls back gracefully to
in-memory when Redis is not configured (local dev without Redis).
"""

import os
from collections.abc import Callable

from slowapi import Limiter
from slowapi.util import get_remote_address

# TESTING=true (CI): bypass per-endpoint limits so slowapi doesn't interfere with assertions.
_testing = os.getenv("TESTING", "false").lower() == "true"

# Redis storage URI assembled from env vars to avoid circular import with config.py.
_redis_host = os.getenv("REDIS_HOST", "")
_redis_port = os.getenv("REDIS_PORT", "6379")
_redis_password = os.getenv("REDIS_PASSWORD", "")
# TLS-only providers (e.g. Upstash) need the rediss:// scheme instead of redis://.
_redis_ssl = os.getenv("REDIS_SSL", "false").lower() in {"1", "true", "yes"}
_redis_scheme = "rediss" if _redis_ssl else "redis"

if _redis_host and not _testing:
    # Build authenticated URI when password is set, plain URI otherwise.
    if _redis_password:
        _storage_uri = f"{_redis_scheme}://:{_redis_password}@{_redis_host}:{_redis_port}/0"
    else:
        _storage_uri = f"{_redis_scheme}://{_redis_host}:{_redis_port}/0"
    limiter = Limiter(key_func=get_remote_address, storage_uri=_storage_uri)
else:
    # Local dev (no Redis) or CI — use in-memory storage.
    limiter = Limiter(key_func=get_remote_address)


def rate_limit(limit_string: str) -> Callable:
    """Apply a slowapi rate limit; full no-op when TESTING=true."""
    if _testing:
        return lambda f: f  # pass-through, no rate limit applied
    return limiter.limit(limit_string)
