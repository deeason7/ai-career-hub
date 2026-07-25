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


@pytest.mark.asyncio
async def test_delete_resume_cascades_to_cover_letters(
    client: AsyncClient, auth_headers: dict, active_resume: str
):
    """A resume with letters attached deletes cleanly — resume_id is NOT NULL,
    so the ORM has to remove the letters rather than try to unlink them."""
    import uuid
    from datetime import UTC, datetime, timedelta

    from sqlmodel import Session

    from app.core.db import sync_engine
    from app.models.cover_letter import CoverLetter
    from app.models.resume import Resume

    resume_id = uuid.UUID(active_resume)
    with Session(sync_engine) as session:
        letter = CoverLetter(
            user_id=session.get(Resume, resume_id).user_id,
            resume_id=resume_id,
            job_description="attached to the resume under test",
            expires_at=datetime.now(UTC) + timedelta(days=15),
        )
        session.add(letter)
        session.commit()
        letter_id = letter.id

    with patch("app.api.v1.endpoints.resumes._delete_embeddings_bg"):
        resp = await client.delete(f"/api/v1/resumes/{resume_id}", headers=auth_headers)

    assert resp.status_code == 204
    with Session(sync_engine) as session:
        assert session.get(CoverLetter, letter_id) is None
