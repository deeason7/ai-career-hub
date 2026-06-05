"""Shared async fixtures: one engine and one session-scoped loop for the suite."""

import uuid

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.core.db import get_async_session
from app.main import app

# One engine for the whole run. Per-module engines bound to pytest-asyncio's
# default per-test loop, which closed between modules -> "Event loop is closed".
# pytest.ini pins the fixture/test loop scope to session so this stays valid.
TEST_ENGINE = create_async_engine(settings.SQLALCHEMY_ASYNC_DATABASE_URI, pool_pre_ping=True)
TestSessionLocal = async_sessionmaker(bind=TEST_ENGINE, class_=AsyncSession, expire_on_commit=False)


async def _override_session():
    async with TestSessionLocal() as session:
        yield session


app.dependency_overrides[get_async_session] = _override_session


@pytest_asyncio.fixture(scope="session", autouse=True)
async def setup_db():
    """Start each run from a clean schema and tear it down afterwards."""
    import app.models  # noqa: F401 — register every table before create_all

    async with TEST_ENGINE.begin() as conn:
        await conn.run_sync(SQLModel.metadata.drop_all)
        await conn.run_sync(SQLModel.metadata.create_all)
    yield
    async with TEST_ENGINE.begin() as conn:
        await conn.run_sync(SQLModel.metadata.drop_all)
    await TEST_ENGINE.dispose()


@pytest_asyncio.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture
async def auth_token(client: AsyncClient) -> str:
    """Register a unique user and return a bearer access token."""
    email = f"user_{uuid.uuid4().hex[:8]}@example.com"
    await client.post(
        "/api/v1/auth/register",
        json={"email": email, "full_name": "Test User", "password": "Testpassword99!"},
    )
    login = await client.post(
        "/api/v1/auth/login", data={"username": email, "password": "Testpassword99!"}
    )
    return login.json()["access_token"]


@pytest_asyncio.fixture
async def auth_headers(auth_token: str) -> dict:
    """Authorization header for a freshly registered user."""
    return {"Authorization": f"Bearer {auth_token}"}


@pytest_asyncio.fixture
async def active_resume(client: AsyncClient, auth_headers: dict) -> str:
    """Insert an active resume for the authenticated user and return its id."""
    from app.models.resume import Resume

    me = await client.get("/api/v1/auth/me", headers=auth_headers)
    user_id = uuid.UUID(me.json()["id"])
    async with TestSessionLocal() as session:
        resume = Resume(
            user_id=user_id,
            name="Test Resume",
            original_filename="resume.pdf",
            raw_text="Experienced Python engineer with 5 years building APIs.",
            is_active=True,
        )
        session.add(resume)
        await session.commit()
        await session.refresh(resume)
    return str(resume.id)
