import logging
import os
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import bcrypt
import jwt
import redis.asyncio as aioredis
from redis.exceptions import RedisError

from app.core.config import settings

ALGORITHM = "HS256"
REFRESH_TOKEN_EXPIRE_DAYS = 7

logger = logging.getLogger(__name__)


def get_password_hash(password: str) -> str:
    """Return a bcrypt hash of the given plaintext password."""
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Return True if plaintext matches the stored bcrypt hash."""
    return bcrypt.checkpw(plain_password.encode(), hashed_password.encode())


def create_access_token(subject: Any, expires_delta: timedelta | None = None) -> str:
    """Mint a short-lived HS256 access token (default: ACCESS_TOKEN_EXPIRE_MINUTES)."""
    expire = datetime.now(UTC) + (
        expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode = {
        "exp": expire,
        "sub": str(subject),
        "type": "access",
        "jti": str(uuid.uuid4()),
    }
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=ALGORITHM)


def create_refresh_token(subject: Any) -> str:
    """Mint a 7-day refresh token with a unique JTI for revocation tracking."""
    expire = datetime.now(UTC) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode = {
        "exp": expire,
        "sub": str(subject),
        "type": "refresh",
        "jti": str(uuid.uuid4()),
    }
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=ALGORITHM)


def verify_token(token: str, token_type: str = "access") -> tuple[str, str] | None:
    """Decode and validate a JWT; return (subject, jti) or None."""
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("type") != token_type:
            return None
        sub = payload.get("sub")
        jti = payload.get("jti")
        if not sub or not jti:
            return None
        return sub, jti
    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
        return None


def verify_refresh_token(token: str) -> tuple[str, str] | None:
    """Decode a refresh token; return (user_id, jti) or None."""
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("type") != "refresh":
            return None
        sub = payload.get("sub")
        jti = payload.get("jti")
        if not sub or not jti:
            return None
        return sub, jti
    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
        return None


_redis: aioredis.Redis | None = None


def _get_redis() -> aioredis.Redis | None:
    """Return the module-level Redis client, initialised lazily on first call."""
    global _redis
    if _redis is not None:
        return _redis
    host = os.getenv("REDIS_HOST", "")
    if not host:
        return None
    port = int(os.getenv("REDIS_PORT", "6379"))
    password = os.getenv("REDIS_PASSWORD") or None
    auth = f":{password}@" if password else ""
    ssl = os.getenv("REDIS_SSL", "false").lower() in {"1", "true", "yes"}
    scheme = "rediss" if ssl else "redis"
    _redis = aioredis.from_url(
        f"{scheme}://{auth}{host}:{port}/1",
        encoding="utf-8",
        decode_responses=True,
        max_connections=5,
    )
    return _redis


async def revoke_token(jti: str, ttl_seconds: int) -> None:
    client = _get_redis()
    if not client:
        return
    try:
        await client.setex(f"revoked:{jti}", ttl_seconds, "1")
    except (RedisError, OSError) as exc:
        # Fail open to match is_token_revoked: a Redis hiccup shouldn't 500 a
        # logout. The token simply stays valid until it expires on its own.
        logger.warning("could not revoke jti=%s; it will expire naturally: %s", jti, exc)


async def is_token_revoked(jti: str) -> bool:
    client = _get_redis()
    if not client:
        return False
    try:
        return await client.exists(f"revoked:{jti}") == 1
    except (RedisError, OSError) as exc:
        # Fail open: a Redis outage must not lock out every authenticated user.
        # A revoked token may be honored until its short TTL lapses; log it.
        logger.warning("revocation check failed for jti=%s; allowing request: %s", jti, exc)
        return False
