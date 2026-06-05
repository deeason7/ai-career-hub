"""Refresh-token rotation and logout revocation (single-use refresh, access deny-list)."""

import uuid
from contextlib import contextmanager
from unittest.mock import patch

import pytest
from httpx import AsyncClient

PASSWORD = "Testpassword99!"


class _FakeRedis:
    """In-memory stand-in for the revocation deny-list (setex/exists only)."""

    def __init__(self) -> None:
        self._keys: set[str] = set()

    async def setex(self, key: str, ttl: int, value: str) -> None:
        self._keys.add(key)

    async def exists(self, key: str) -> int:
        return 1 if key in self._keys else 0


@contextmanager
def _fake_denylist():
    """Back revoke_token/is_token_revoked with one shared in-memory store."""
    with patch("app.core.security._get_redis", return_value=_FakeRedis()):
        yield


async def _register_and_login(client: AsyncClient) -> tuple[str, str]:
    """Return (access_token, refresh_token) for a freshly registered user."""
    email = f"user_{uuid.uuid4().hex[:8]}@example.com"
    await client.post(
        "/api/v1/auth/register",
        json={"email": email, "full_name": "Test User", "password": PASSWORD},
    )
    login = await client.post("/api/v1/auth/login", data={"username": email, "password": PASSWORD})
    return login.json()["access_token"], login.cookies.get("refresh_token")


async def _refresh(client: AsyncClient, refresh_token: str):
    """POST /refresh with exactly the given cookie (reset the jar to avoid bleed)."""
    client.cookies.clear()
    client.cookies.set("refresh_token", refresh_token)
    return await client.post("/api/v1/auth/refresh")


@pytest.mark.asyncio
async def test_refresh_rotates_the_cookie(client: AsyncClient):
    with _fake_denylist():
        _, refresh = await _register_and_login(client)
        resp = await _refresh(client, refresh)
        assert resp.status_code == 200
        assert resp.json()["access_token"]
        rotated = resp.cookies.get("refresh_token")
        assert rotated and rotated != refresh


@pytest.mark.asyncio
async def test_refreshed_access_token_authenticates(client: AsyncClient):
    with _fake_denylist():
        _, refresh = await _register_and_login(client)
        new_access = (await _refresh(client, refresh)).json()["access_token"]
        me = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {new_access}"})
        assert me.status_code == 200


@pytest.mark.asyncio
async def test_old_refresh_token_rejected_after_rotation(client: AsyncClient):
    with _fake_denylist():
        _, refresh = await _register_and_login(client)
        assert (await _refresh(client, refresh)).status_code == 200
        # Re-presenting the now rotated-out token must be refused.
        assert (await _refresh(client, refresh)).status_code == 401


@pytest.mark.asyncio
async def test_rotated_refresh_token_still_works(client: AsyncClient):
    with _fake_denylist():
        _, refresh = await _register_and_login(client)
        new_refresh = (await _refresh(client, refresh)).cookies.get("refresh_token")
        assert (await _refresh(client, new_refresh)).status_code == 200


@pytest.mark.asyncio
async def test_refresh_without_cookie_returns_401(client: AsyncClient):
    with _fake_denylist():
        client.cookies.clear()
        assert (await client.post("/api/v1/auth/refresh")).status_code == 401


@pytest.mark.asyncio
async def test_logout_revokes_the_access_token(client: AsyncClient):
    with _fake_denylist():
        access, refresh = await _register_and_login(client)
        headers = {"Authorization": f"Bearer {access}"}
        assert (await client.get("/api/v1/auth/me", headers=headers)).status_code == 200

        client.cookies.clear()
        client.cookies.set("refresh_token", refresh)
        logout = await client.post("/api/v1/auth/logout", headers=headers)
        assert logout.status_code == 204
        # The same access token is now deny-listed and rejected per request.
        assert (await client.get("/api/v1/auth/me", headers=headers)).status_code == 401


@pytest.mark.asyncio
async def test_logout_without_access_token_still_succeeds(client: AsyncClient):
    with _fake_denylist():
        _, refresh = await _register_and_login(client)
        client.cookies.clear()
        client.cookies.set("refresh_token", refresh)
        logout = await client.post("/api/v1/auth/logout")
        assert logout.status_code == 204
