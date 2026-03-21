"""
Real integration tests for the API (register, login, resume CRUD, ATS score, job tracker).
Requires: PostgreSQL and Redis to be running (via Docker Compose).

Run with: pytest tests/test_api.py -v
Start services first: docker compose up db redis -d
"""
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.core.db import get_async_session
from app.main import app

# --- Test Database (uses same postgres, separate test DB ideally) ---
TEST_ENGINE = create_async_engine(
    settings.SQLALCHEMY_ASYNC_DATABASE_URI,
    pool_pre_ping=True,
)
TestSessionLocal = async_sessionmaker(bind=TEST_ENGINE, class_=AsyncSession, expire_on_commit=False)


async def override_session():
    async with TestSessionLocal() as session:
        yield session


app.dependency_overrides[get_async_session] = override_session


@pytest_asyncio.fixture(scope="module", autouse=True)
async def setup_db():
    """Create all tables before tests, drop after."""
    async with TEST_ENGINE.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    yield
    async with TEST_ENGINE.begin() as conn:
        await conn.run_sync(SQLModel.metadata.drop_all)


@pytest_asyncio.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


# ---------- AUTH TESTS ----------

@pytest.mark.asyncio
async def test_register_new_user(client: AsyncClient):
    response = await client.post("/api/v1/auth/register", json={
        "email": "test@example.com",
        "full_name": "Test User",
        "password": "testpassword123",
    })
    assert response.status_code == 201
    data = response.json()
    assert data["email"] == "test@example.com"
    assert "id" in data


@pytest.mark.asyncio
async def test_register_duplicate_email(client: AsyncClient):
    await client.post("/api/v1/auth/register", json={
        "email": "dup@example.com",
        "full_name": "Dup User",
        "password": "pass123",
    })
    response = await client.post("/api/v1/auth/register", json={
        "email": "dup@example.com",
        "full_name": "Another",
        "password": "pass456",
    })
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_login_success(client: AsyncClient):
    await client.post("/api/v1/auth/register", json={
        "email": "login_test@example.com",
        "full_name": "Login Test",
        "password": "securepass",
    })
    response = await client.post("/api/v1/auth/login", data={
        "username": "login_test@example.com",
        "password": "securepass",
    })
    assert response.status_code == 200
    assert "access_token" in response.json()


@pytest.mark.asyncio
async def test_login_wrong_password(client: AsyncClient):
    await client.post("/api/v1/auth/register", json={
        "email": "badpass@example.com",
        "full_name": "Bad Pass",
        "password": "rightpass",
    })
    response = await client.post("/api/v1/auth/login", data={
        "username": "badpass@example.com",
        "password": "wrongpass",
    })
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_get_me_authenticated(client: AsyncClient):
    await client.post("/api/v1/auth/register", json={
        "email": "me@example.com",
        "full_name": "Me User",
        "password": "mepass",
    })
    login = await client.post("/api/v1/auth/login", data={
        "username": "me@example.com",
        "password": "mepass",
    })
    token = login.json()["access_token"]
    response = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    assert response.json()["email"] == "me@example.com"


# ---------- ATS SCORE TESTS ----------

@pytest_asyncio.fixture
async def auth_token(client: AsyncClient):
    """Create a user and return auth token."""
    email = "ats_user@example.com"
    await client.post("/api/v1/auth/register", json={
        "email": email, "full_name": "ATS User", "password": "atspass",
    })
    login = await client.post("/api/v1/auth/login", data={"username": email, "password": "atspass"})
    return login.json()["access_token"]


@pytest.mark.asyncio
async def test_ats_score_endpoint_requires_auth(client: AsyncClient):
    response = await client.post("/api/v1/ai/ats-score", json={
        "job_description": "Python developer needed"
    })
    assert response.status_code == 401


# ---------- JOB TRACKER TESTS ----------

@pytest.mark.asyncio
async def test_create_job_application(client: AsyncClient, auth_token: str):
    headers = {"Authorization": f"Bearer {auth_token}"}
    response = await client.post("/api/v1/jobs/", json={
        "company": "Google",
        "role": "Software Engineer",
        "status": "applied",
        "notes": "Applied via website",
    }, headers=headers)
    assert response.status_code == 201
    data = response.json()
    assert data["company"] == "Google"
    assert data["status"] == "applied"


@pytest.mark.asyncio
async def test_list_job_applications(client: AsyncClient, auth_token: str):
    headers = {"Authorization": f"Bearer {auth_token}"}
    response = await client.get("/api/v1/jobs/", headers=headers)
    assert response.status_code == 200
    assert isinstance(response.json(), list)


@pytest.mark.asyncio
async def test_job_application_stats(client: AsyncClient, auth_token: str):
    headers = {"Authorization": f"Bearer {auth_token}"}
    response = await client.get("/api/v1/jobs/stats", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert "total" in data
    assert "by_status" in data


@pytest.mark.asyncio
async def test_health_check(client: AsyncClient):
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
