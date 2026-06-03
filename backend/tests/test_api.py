"""
Real integration tests for the API (register, login, resume CRUD, ATS score, job tracker).
Requires: PostgreSQL running (Docker Compose).

Run with: pytest tests/test_api.py -v
Start services first: docker compose up db -d
"""

import pytest
from httpx import AsyncClient

# ---------- AUTH TESTS ----------


@pytest.mark.asyncio
async def test_register_new_user(client: AsyncClient):
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "test@example.com",
            "full_name": "Test User",
            "password": "Testpassword1!",
        },
    )
    assert response.status_code == 201
    data = response.json()
    assert data["email"] == "test@example.com"
    assert "id" in data


@pytest.mark.asyncio
async def test_register_duplicate_email(client: AsyncClient):
    await client.post(
        "/api/v1/auth/register",
        json={
            "email": "dup@example.com",
            "full_name": "Dup User",
            "password": "Passw0rd1234!",
        },
    )
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "dup@example.com",
            "full_name": "Another",
            "password": "Passw0rd5678!",
        },
    )
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_login_success(client: AsyncClient):
    await client.post(
        "/api/v1/auth/register",
        json={
            "email": "login_test@example.com",
            "full_name": "Login Test",
            "password": "SecurePass12!",
        },
    )
    response = await client.post(
        "/api/v1/auth/login",
        data={
            "username": "login_test@example.com",
            "password": "SecurePass12!",
        },
    )
    assert response.status_code == 200
    assert "access_token" in response.json()


@pytest.mark.asyncio
async def test_login_wrong_password(client: AsyncClient):
    await client.post(
        "/api/v1/auth/register",
        json={
            "email": "badpass@example.com",
            "full_name": "Bad Pass",
            "password": "RightPass12!",
        },
    )
    response = await client.post(
        "/api/v1/auth/login",
        data={
            "username": "badpass@example.com",
            "password": "WrongPass12!",
        },
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_get_me_authenticated(client: AsyncClient):
    await client.post(
        "/api/v1/auth/register",
        json={
            "email": "me@example.com",
            "full_name": "Me User",
            "password": "Mepassword12!",
        },
    )
    login = await client.post(
        "/api/v1/auth/login",
        data={
            "username": "me@example.com",
            "password": "Mepassword12!",
        },
    )
    token = login.json()["access_token"]
    response = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    assert response.json()["email"] == "me@example.com"


# ---------- ATS SCORE TESTS ----------


@pytest.mark.asyncio
async def test_ats_score_endpoint_requires_auth(client: AsyncClient):
    response = await client.post(
        "/api/v1/ai/ats-score", json={"job_description": "Python developer needed"}
    )
    assert response.status_code == 401


# ---------- JOB TRACKER TESTS ----------


@pytest.mark.asyncio
async def test_create_job_application(client: AsyncClient, auth_token: str):
    headers = {"Authorization": f"Bearer {auth_token}"}
    response = await client.post(
        "/api/v1/jobs/",
        json={
            "company": "Google",
            "role": "Software Engineer",
            "status": "applied",
            "notes": "Applied via website",
        },
        headers=headers,
    )
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
