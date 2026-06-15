"""Shared async fixtures: one engine and one session-scoped loop for the suite."""

import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.exc import OperationalError
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


async def _ensure_test_database() -> None:
    """Create the test database if it's missing (local first run); no-op when it exists (CI)."""
    probe = create_async_engine(settings.SQLALCHEMY_ASYNC_DATABASE_URI)
    try:
        async with probe.connect():
            return
    except OperationalError:
        pass  # database doesn't exist yet — create it below
    finally:
        await probe.dispose()

    admin_url = (
        f"postgresql+psycopg_async://{settings.POSTGRES_USER}:{settings.POSTGRES_PASSWORD}"
        f"@{settings.POSTGRES_SERVER}:{settings.POSTGRES_PORT}/postgres"
    )
    admin = create_async_engine(admin_url, isolation_level="AUTOCOMMIT")
    try:
        async with admin.connect() as conn:
            await conn.execute(text(f'CREATE DATABASE "{settings.POSTGRES_DB}"'))
    finally:
        await admin.dispose()


@pytest_asyncio.fixture(scope="session", autouse=True)
async def setup_db():
    """Start each run from a clean schema and tear it down afterwards."""
    import app.models  # noqa: F401 — register every table before create_all

    await _ensure_test_database()
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


class _FakeRedisSync:
    """In-memory stand-in for the sync hash ops task_state uses."""

    def __init__(self, data: dict):
        self.data = data

    def hset(self, key, mapping=None):
        self.data.setdefault(key, {}).update(mapping or {})

    def hgetall(self, key):
        return dict(self.data.get(key, {}))

    def expire(self, key, ttl):
        return True


class _FakeRedisAsync:
    """Async twin of _FakeRedisSync over the same storage dict."""

    def __init__(self, data: dict):
        self.data = data

    async def hset(self, key, mapping=None):
        self.data.setdefault(key, {}).update(mapping or {})

    async def hgetall(self, key):
        return dict(self.data.get(key, {}))

    async def expire(self, key, ttl):
        return True


@pytest.fixture
def fake_task_store(monkeypatch):
    """Route task_state at an in-memory fake so tests don't need a live Redis.

    Async handlers and sync background tasks see the same storage, mirroring
    how both real clients point at the same Redis DB.
    """
    from app.services import task_state

    data: dict[str, dict] = {}
    monkeypatch.setattr(task_state, "_get_redis", lambda: _FakeRedisAsync(data))
    monkeypatch.setattr(task_state, "_get_redis_sync", lambda: _FakeRedisSync(data))
    return data


@pytest.fixture
def no_task_store(monkeypatch):
    """Simulate Redis being unavailable — endpoints should fall back inline."""
    from app.services import task_state

    monkeypatch.setattr(task_state, "_get_redis", lambda: None)
    monkeypatch.setattr(task_state, "_get_redis_sync", lambda: None)


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
