"""Tests for cover letter refinement endpoints."""

import uuid
from unittest.mock import patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.core.db import get_async_session
from app.main import app

TEST_ENGINE = create_async_engine(settings.SQLALCHEMY_ASYNC_DATABASE_URI, pool_pre_ping=True)
TestSessionLocal = async_sessionmaker(bind=TEST_ENGINE, class_=AsyncSession, expire_on_commit=False)


async def override_session():
    async with TestSessionLocal() as session:
        yield session


app.dependency_overrides[get_async_session] = override_session


@pytest_asyncio.fixture(scope="module", autouse=True)
async def setup_db():
    async with TEST_ENGINE.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    yield
    async with TEST_ENGINE.begin() as conn:
        await conn.run_sync(SQLModel.metadata.drop_all)


@pytest_asyncio.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture
async def auth_headers(client: AsyncClient):
    email = f"refine_{uuid.uuid4().hex[:8]}@example.com"
    await client.post(
        "/api/v1/auth/register",
        json={"email": email, "full_name": "Refine User", "password": "testpass99"},
    )
    login = await client.post(
        "/api/v1/auth/login", data={"username": email, "password": "testpass99"}
    )
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


@pytest_asyncio.fixture
async def cover_letter_id(client: AsyncClient, auth_headers: dict):
    """Create a cover letter in 'success' state and return its UUID string."""
    import io

    from sqlmodel import Session

    from app.core.db import sync_engine
    from app.models.cover_letter import CoverLetter

    # Upload a resume first
    resume_content = b"Python developer with 3 years of experience in FastAPI and PostgreSQL."
    response = await client.post(
        "/api/v1/resumes/",
        files={"file": ("resume.txt", io.BytesIO(resume_content), "text/plain")},
        data={"name": "Test Resume"},
        headers=auth_headers,
    )
    assert response.status_code == 201
    resume_id = response.json()["id"]

    # Generate a cover letter
    gen = await client.post(
        "/api/v1/cover-letters/generate",
        json={"job_description": "We need a Python backend engineer.", "resume_id": resume_id},
        headers=auth_headers,
    )
    assert gen.status_code == 202
    cl_id = gen.json()["id"]

    # Manually set status + text so refinement can run (bg task won't execute in test)
    with Session(sync_engine) as session:
        cl = session.get(CoverLetter, uuid.UUID(cl_id))
        if cl:
            cl.status = "success"
            cl.generated_text = "Dear Hiring Manager, I am excited to apply for the Python backend role."
            session.add(cl)
            session.commit()

    return cl_id


# --- Refine endpoint ---

@pytest.mark.asyncio
async def test_refine_requires_auth(client: AsyncClient):
    fake_id = uuid.uuid4()
    response = await client.post(
        f"/api/v1/cover-letters/{fake_id}/refine",
        json={"command": "Make it shorter"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_refine_returns_202(client: AsyncClient, auth_headers: dict, cover_letter_id: str):
    with patch("app.api.v1.endpoints.cover_letters._run_refine_bg"):
        response = await client.post(
            f"/api/v1/cover-letters/{cover_letter_id}/refine",
            json={"command": "Make it more formal"},
            headers=auth_headers,
        )
    assert response.status_code == 202
    data = response.json()
    assert data["cover_letter_id"] == cover_letter_id
    assert data["version_number"] == 1
    assert data["user_command"] == "Make it more formal"


@pytest.mark.asyncio
async def test_refine_increments_version(
    client: AsyncClient, auth_headers: dict, cover_letter_id: str
):
    with patch("app.api.v1.endpoints.cover_letters._run_refine_bg"):
        r1 = await client.post(
            f"/api/v1/cover-letters/{cover_letter_id}/refine",
            json={"command": "Shorten paragraph two"},
            headers=auth_headers,
        )
        r2 = await client.post(
            f"/api/v1/cover-letters/{cover_letter_id}/refine",
            json={"command": "Add more enthusiasm"},
            headers=auth_headers,
        )
    assert r1.status_code == 202
    assert r2.status_code == 202
    assert r2.json()["version_number"] > r1.json()["version_number"]


@pytest.mark.asyncio
async def test_refine_not_found(client: AsyncClient, auth_headers: dict):
    fake_id = uuid.uuid4()
    response = await client.post(
        f"/api/v1/cover-letters/{fake_id}/refine",
        json={"command": "Make it shorter"},
        headers=auth_headers,
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_refine_command_too_short(
    client: AsyncClient, auth_headers: dict, cover_letter_id: str
):
    response = await client.post(
        f"/api/v1/cover-letters/{cover_letter_id}/refine",
        json={"command": "Hi"},
        headers=auth_headers,
    )
    assert response.status_code == 422


# --- List revisions endpoint ---

@pytest.mark.asyncio
async def test_list_revisions_returns_list(
    client: AsyncClient, auth_headers: dict, cover_letter_id: str
):
    response = await client.get(
        f"/api/v1/cover-letters/{cover_letter_id}/revisions",
        headers=auth_headers,
    )
    assert response.status_code == 200
    assert isinstance(response.json(), list)


@pytest.mark.asyncio
async def test_list_revisions_requires_auth(client: AsyncClient, cover_letter_id: str):
    response = await client.get(f"/api/v1/cover-letters/{cover_letter_id}/revisions")
    assert response.status_code == 401


# --- Activate revision endpoint ---

@pytest.mark.asyncio
async def test_activate_revision(
    client: AsyncClient, auth_headers: dict, cover_letter_id: str
):
    with patch("app.api.v1.endpoints.cover_letters._run_refine_bg"):
        refine = await client.post(
            f"/api/v1/cover-letters/{cover_letter_id}/refine",
            json={"command": "Use a more confident tone"},
            headers=auth_headers,
        )
    assert refine.status_code == 202
    version = refine.json()["version_number"]

    activate = await client.post(
        f"/api/v1/cover-letters/{cover_letter_id}/revisions/{version}/activate",
        headers=auth_headers,
    )
    assert activate.status_code == 200
    assert activate.json()["id"] == cover_letter_id


@pytest.mark.asyncio
async def test_activate_nonexistent_revision(
    client: AsyncClient, auth_headers: dict, cover_letter_id: str
):
    response = await client.post(
        f"/api/v1/cover-letters/{cover_letter_id}/revisions/9999/activate",
        headers=auth_headers,
    )
    assert response.status_code == 404
