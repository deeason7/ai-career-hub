import os
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import bcrypt
import jwt
import redis.asyncio as aioredis

from app.core.config import settings

ALGORITHM = "HS256"
REFRESH_TOKEN_EXPIRE_DAYS = 7


def get_password_hash(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(plain_password.encode(), hashed_password.encode())


def create_access_token(subject: Any, expires_delta: timedelta | None = None) -> str:
    expire = datetime.now(UTC) + (
        expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode = {"exp": expire, "sub": str(subject), "type": "access"}
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=ALGORITHM)


def create_refresh_token(subject: Any) -> str:
    expire = datetime.now(UTC) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode = {
        "exp": expire,
        "sub": str(subject),
        "type": "refresh",
        "jti": str(uuid.uuid4()),
    }
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=ALGORITHM)


def verify_token(token: str, token_type: str = "access") -> str | None:
    """Decode and validate a JWT; return the subject (user ID) or None."""
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("type") != token_type:
            return None
        return payload.get("sub")
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


def _get_redis_client() -> aioredis.Redis | None:
    host = os.getenv("REDIS_HOST", "")
    if not host:
        return None
    port = int(os.getenv("REDIS_PORT", "6379"))
    password = os.getenv("REDIS_PASSWORD") or None
    return aioredis.Redis(host=host, port=port, password=password, db=1, decode_responses=True)


async def revoke_token(jti: str, ttl_seconds: int) -> None:
    client = _get_redis_client()
    if client:
        async with client:
            await client.setex(f"revoked:{jti}", ttl_seconds, "1")


async def is_token_revoked(jti: str) -> bool:
    client = _get_redis_client()
    if not client:
        return False
    async with client:
        return await client.exists(f"revoked:{jti}") == 1
