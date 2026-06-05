"""Tests for resume deletion and its background cleanup."""

import io
from unittest.mock import patch

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_delete_resume_returns_204_and_queues_cleanup(
    client: AsyncClient, auth_headers: dict
):
    content = b"Python developer with FastAPI and PostgreSQL experience."
    upload = await client.post(
        "/api/v1/resumes/upload",
        files={"file": ("resume.txt", io.BytesIO(content), "text/plain")},
        data={"name": "Delete Me"},
        headers=auth_headers,
    )
    assert upload.status_code == 201
    resume_id = upload.json()["id"]

    with patch("app.api.v1.endpoints.resumes._delete_embeddings_bg") as mock_cleanup:
        resp = await client.delete(f"/api/v1/resumes/{resume_id}", headers=auth_headers)

    assert resp.status_code == 204
    mock_cleanup.assert_called_once()
