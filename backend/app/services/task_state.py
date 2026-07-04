"""Redis-backed state for async background tasks (job match, agent runs)."""

import json
import logging
import os
import uuid
from typing import Any
from urllib.parse import quote

import redis
import redis.asyncio as aioredis

logger = logging.getLogger(__name__)

# Results are recomputable, so an hour comfortably outlives any polling UI session.
TASK_TTL_SECONDS = 3600

# Each step is its own hash field — parallel workers can flip their own step
# without a read-modify-write race on a shared JSON blob.
_STEP_PREFIX = "step:"

_redis: aioredis.Redis | None = None
_redis_sync: redis.Redis | None = None


def _redis_url() -> str | None:
    host = os.getenv("REDIS_HOST", "")
    if not host:
        return None
    port = int(os.getenv("REDIS_PORT", "6379"))
    password = os.getenv("REDIS_PASSWORD") or None
    auth = f":{quote(password, safe='')}@" if password else ""
    ssl = os.getenv("REDIS_SSL", "false").lower() in {"1", "true", "yes"}
    scheme = "rediss" if ssl else "redis"
    # DB 2 keeps task state apart from the token deny-list (DB 1) on a real
    # Redis; single-database providers like Upstash only allow DB 0.
    db = os.getenv("REDIS_DB_TASKS", "2")
    return f"{scheme}://{auth}{host}:{port}/{db}"


def _get_redis() -> aioredis.Redis | None:
    """Return the module-level async Redis client, initialised lazily on first call."""
    global _redis
    if _redis is not None:
        return _redis
    url = _redis_url()
    if url is None:
        return None
    _redis = aioredis.from_url(url, encoding="utf-8", decode_responses=True, max_connections=5)
    return _redis


def _get_redis_sync() -> redis.Redis | None:
    """Return the sync Redis client for threadpool writers (sync background tasks).

    The async client is bound to the event loop, so code running in worker
    threads — where BackgroundTasks executes sync functions — must use this one.
    """
    global _redis_sync
    if _redis_sync is not None:
        return _redis_sync
    url = _redis_url()
    if url is None:
        return None
    _redis_sync = redis.Redis.from_url(
        url, encoding="utf-8", decode_responses=True, max_connections=5
    )
    return _redis_sync


def _key(task_id: str) -> str:
    return f"task:{task_id}"


async def create(kind: str, user_id: Any, steps: list[str] | None = None) -> str | None:
    """Register a new task and return its id, or None when Redis can't take it."""
    client = _get_redis()
    if client is None:
        return None
    task_id = str(uuid.uuid4())
    fields = {"kind": kind, "user_id": str(user_id), "status": "PENDING"}
    for step in steps or []:
        fields[f"{_STEP_PREFIX}{step}"] = "pending"
    try:
        await client.hset(_key(task_id), mapping=fields)
        await client.expire(_key(task_id), TASK_TTL_SECONDS)
    except redis.RedisError as exc:
        logger.warning("task store unavailable (%s) — caller should run inline", exc)
        return None
    return task_id


async def set_status(task_id: str, status: str, error: str | None = None) -> None:
    """Move a task to a new status; best-effort (a dropped write reads as 'lost')."""
    client = _get_redis()
    if client is None:
        return
    fields = {"status": status}
    if error:
        fields["error"] = error
    try:
        await client.hset(_key(task_id), mapping=fields)
    except redis.RedisError as exc:
        logger.warning("could not move task %s to %s: %s", task_id, status, exc)


async def set_step(task_id: str, step: str, state: str) -> None:
    """Record one step's state (pending/running/done/failed); best-effort."""
    client = _get_redis()
    if client is None:
        return
    try:
        await client.hset(_key(task_id), mapping={f"{_STEP_PREFIX}{step}": state})
    except redis.RedisError as exc:
        logger.warning("could not record step %s=%s on task %s: %s", step, state, task_id, exc)


async def set_result(task_id: str, result: dict) -> None:
    """Store the final payload and mark the task SUCCESS; best-effort."""
    client = _get_redis()
    if client is None:
        return
    try:
        await client.hset(
            _key(task_id), mapping={"status": "SUCCESS", "result": json.dumps(result)}
        )
    except redis.RedisError as exc:
        logger.warning("could not store result for task %s: %s", task_id, exc)


def set_status_sync(task_id: str, status: str, error: str | None = None) -> None:
    """set_status for sync (threadpool) contexts; best-effort like its async twin."""
    client = _get_redis_sync()
    if client is None:
        return
    fields = {"status": status}
    if error:
        fields["error"] = error
    try:
        client.hset(_key(task_id), mapping=fields)
    except redis.RedisError as exc:
        logger.warning("could not move task %s to %s: %s", task_id, status, exc)


def set_step_sync(task_id: str, step: str, state: str) -> None:
    """set_step for sync (threadpool) contexts; best-effort."""
    client = _get_redis_sync()
    if client is None:
        return
    try:
        client.hset(_key(task_id), mapping={f"{_STEP_PREFIX}{step}": state})
    except redis.RedisError as exc:
        logger.warning("could not record step %s=%s on task %s: %s", step, state, task_id, exc)


def set_result_sync(task_id: str, result: dict) -> None:
    """set_result for sync (threadpool) contexts; best-effort."""
    client = _get_redis_sync()
    if client is None:
        return
    try:
        client.hset(_key(task_id), mapping={"status": "SUCCESS", "result": json.dumps(result)})
    except redis.RedisError as exc:
        logger.warning("could not store result for task %s: %s", task_id, exc)


def set_meta_sync(task_id: str, meta: dict) -> None:
    """Attach small mid-run metadata (e.g. what the scraper read); best-effort."""
    client = _get_redis_sync()
    if client is None:
        return
    try:
        client.hset(_key(task_id), mapping={"meta": json.dumps(meta)})
    except redis.RedisError as exc:
        logger.warning("could not record meta on task %s: %s", task_id, exc)


async def get(task_id: str) -> dict | None:
    """Fetch a task as {kind, user_id, status, steps, result, error}; None if unknown.

    Redis errors propagate — the caller decides how to surface unavailability.
    """
    client = _get_redis()
    if client is None:
        return None
    data = await client.hgetall(_key(task_id))
    if not data:
        return None
    steps = {
        name[len(_STEP_PREFIX) :]: state
        for name, state in data.items()
        if name.startswith(_STEP_PREFIX)
    }
    return {
        "kind": data.get("kind"),
        "user_id": data.get("user_id"),
        "status": data.get("status", "PENDING"),
        "steps": steps,
        "result": json.loads(data["result"]) if data.get("result") else None,
        "meta": json.loads(data["meta"]) if data.get("meta") else None,
        "error": data.get("error"),
    }
