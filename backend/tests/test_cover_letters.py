"""Tests for the cover letter generate and poll endpoints."""

import uuid

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_generate_rejects_too_short_jd(client: AsyncClient, auth_headers: dict):
    resp = await client.post(
        "/api/v1/cover-letters/generate",
        json={"job_description": "too short"},
        headers=auth_headers,
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_generate_requires_auth(client: AsyncClient):
    resp = await client.post(
        "/api/v1/cover-letters/generate",
        json={"job_description": "A sufficiently long and perfectly valid job description here."},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_poll_unknown_task_returns_404(client: AsyncClient, auth_headers: dict):
    resp = await client.get(
        f"/api/v1/cover-letters/task/{uuid.uuid4()}",
        headers=auth_headers,
    )
    assert resp.status_code == 404
