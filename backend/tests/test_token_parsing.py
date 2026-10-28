"""Malformed token headers must be rejected before authentication reaches the database."""

import base64

import pytest
from httpx import AsyncClient

from app.core.security import verify_refresh_token, verify_token


def _token_with_nested_header() -> str:
    header = b'{"alg":"HS256","nested":' + b"[" * 2000 + b"0" + b"]" * 2000 + b"}"
    encoded = base64.urlsafe_b64encode(header).rstrip(b"=").decode()
    return f"{encoded}.e30.AA"


@pytest.mark.parametrize("verify", [verify_token, verify_refresh_token])
def test_nested_header_is_rejected(verify):
    assert verify(_token_with_nested_header()) is None


@pytest.mark.asyncio
async def test_profile_rejects_nested_token_header(client: AsyncClient):
    response = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {_token_with_nested_header()}"},
    )
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


@pytest.mark.asyncio
async def test_refresh_rejects_nested_token_header(client: AsyncClient):
    client.cookies.clear()
    client.cookies.set("refresh_token", _token_with_nested_header())
    response = await client.post("/api/v1/auth/refresh")
    assert response.status_code == 401
