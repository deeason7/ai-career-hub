"""Tests for the async job-match endpoint and its task polling."""

import io
import uuid
from unittest.mock import patch

import pytest
import pytest_asyncio
from httpx import AsyncClient

_ATS_PATCH = "app.api.v1.endpoints.analysis.calculate_ats_score"
_SKILL_PATCH = "app.api.v1.endpoints.analysis.generate_skill_gap_analysis"
_INTERVIEW_PATCH = "app.api.v1.endpoints.analysis.generate_interview_questions"

_FAKE_SKILL_GAP = {
    "ats_score": 72.0,
    "matched_skills": ["python"],
    "missing_skills": ["kubernetes"],
    "priority_gaps": ["kubernetes"],
    "learning_recommendations": [],
}

_FAKE_QUESTIONS = ["Tell me about your FastAPI experience.", "How do you handle async IO?"]


def _fake_ats_obj():
    from app.services.ats_scorer import ATSResult

    return ATSResult(
        score=72.0,
        semantic_score=68.0,
        keyword_score=80.0,
        structure_score=60.0,
        matched_keywords=["python", "fastapi"],
        missing_keywords=["kubernetes"],
        recommendations=[],
        section_scores={},
        breakdown={},
    )


@pytest_asyncio.fixture
async def resume_id(client: AsyncClient, auth_headers: dict):
    content = b"Python developer with 3 years FastAPI and PostgreSQL experience."
    resp = await client.post(
        "/api/v1/resumes/upload",
        files={"file": ("resume.txt", io.BytesIO(content), "text/plain")},
        data={"name": "Analysis Resume"},
        headers=auth_headers,
    )
    assert resp.status_code == 201
    return resp.json()["id"]


async def _submit(client: AsyncClient, auth_headers: dict, resume_id: str):
    return await client.post(
        "/api/v1/analysis/job-match",
        json={"resume_id": resume_id, "job_description": "Python backend engineer role"},
        headers=auth_headers,
    )


# ── Auth guards ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_job_match_requires_auth(client: AsyncClient):
    resp = await client.post(
        "/api/v1/analysis/job-match",
        json={"resume_id": str(uuid.uuid4()), "job_description": "Python backend engineer"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_poll_requires_auth(client: AsyncClient):
    resp = await client.get(f"/api/v1/analysis/task/{uuid.uuid4()}")
    assert resp.status_code == 401


# ── 404 for unknown resume ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_job_match_404_for_unknown_resume(client: AsyncClient, auth_headers: dict):
    resp = await client.post(
        "/api/v1/analysis/job-match",
        json={"resume_id": str(uuid.uuid4()), "job_description": "Python backend engineer role"},
        headers=auth_headers,
    )
    assert resp.status_code == 404


# ── Async happy path: 202 → poll → SUCCESS ───────────────────────────────────


@pytest.mark.asyncio
async def test_job_match_returns_202_then_success(
    client: AsyncClient, auth_headers: dict, resume_id: str, fake_task_store
):
    with (
        patch(_ATS_PATCH, return_value=_fake_ats_obj()),
        patch(_SKILL_PATCH, return_value=_FAKE_SKILL_GAP),
        patch(_INTERVIEW_PATCH, return_value=_FAKE_QUESTIONS),
    ):
        resp = await _submit(client, auth_headers, resume_id)

    assert resp.status_code == 202
    body = resp.json()
    assert body["task_id"]
    assert body["status"] == "PENDING"

    # The ASGI test transport runs background tasks before returning, so the
    # task is already terminal by the time we poll.
    poll = await client.get(f"/api/v1/analysis/task/{body['task_id']}", headers=auth_headers)
    assert poll.status_code == 200
    task = poll.json()
    assert task["status"] == "SUCCESS"
    assert task["steps"] == {"ats": "done", "skill_gap": "done", "interview": "done"}
    assert task["result"] is not None


@pytest.mark.asyncio
async def test_job_match_result_shape(
    client: AsyncClient, auth_headers: dict, resume_id: str, fake_task_store
):
    with (
        patch(_ATS_PATCH, return_value=_fake_ats_obj()),
        patch(_SKILL_PATCH, return_value=_FAKE_SKILL_GAP),
        patch(_INTERVIEW_PATCH, return_value=_FAKE_QUESTIONS),
    ):
        resp = await _submit(client, auth_headers, resume_id)

    task_id = resp.json()["task_id"]
    poll = await client.get(f"/api/v1/analysis/task/{task_id}", headers=auth_headers)
    result = poll.json()["result"]

    assert set(result.keys()) == {"ats", "skill_gap", "interview_questions"}
    assert {
        "score",
        "semantic_score",
        "keyword_score",
        "structure_score",
        "matched_keywords",
        "missing_keywords",
        "recommendations",
        "section_scores",
        "breakdown",
    }.issubset(result["ats"].keys())
    assert set(result["skill_gap"].keys()) >= {
        "ats_score",
        "matched_skills",
        "missing_skills",
        "priority_gaps",
        "learning_recommendations",
    }
    assert isinstance(result["interview_questions"], list)


# ── Async failure path ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_job_match_failure_reported_via_poll(
    client: AsyncClient, auth_headers: dict, resume_id: str, fake_task_store
):
    with (
        patch(_ATS_PATCH, side_effect=RuntimeError("model failed")),
        patch(_SKILL_PATCH, return_value=_FAKE_SKILL_GAP),
        patch(_INTERVIEW_PATCH, return_value=_FAKE_QUESTIONS),
    ):
        resp = await _submit(client, auth_headers, resume_id)

    assert resp.status_code == 202
    poll = await client.get(f"/api/v1/analysis/task/{resp.json()['task_id']}", headers=auth_headers)
    task = poll.json()
    assert task["status"] == "FAILURE"
    assert task["error"]
    assert task["result"] is None
    assert task["steps"]["ats"] == "failed"


# ── Poll guards ───────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_poll_unknown_task_404(client: AsyncClient, auth_headers: dict, fake_task_store):
    resp = await client.get(f"/api/v1/analysis/task/{uuid.uuid4()}", headers=auth_headers)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_poll_foreign_task_404(
    client: AsyncClient, auth_headers: dict, resume_id: str, fake_task_store
):
    with (
        patch(_ATS_PATCH, return_value=_fake_ats_obj()),
        patch(_SKILL_PATCH, return_value=_FAKE_SKILL_GAP),
        patch(_INTERVIEW_PATCH, return_value=_FAKE_QUESTIONS),
    ):
        resp = await _submit(client, auth_headers, resume_id)
    task_id = resp.json()["task_id"]

    # A second account must not be able to read the first account's task.
    email = f"user_{uuid.uuid4().hex[:8]}@example.com"
    await client.post(
        "/api/v1/auth/register",
        json={"email": email, "full_name": "Other User", "password": "Testpassword99!"},
    )
    login = await client.post(
        "/api/v1/auth/login", data={"username": email, "password": "Testpassword99!"}
    )
    other_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    poll = await client.get(f"/api/v1/analysis/task/{task_id}", headers=other_headers)
    assert poll.status_code == 404


# ── Inline fallback when Redis is unavailable ─────────────────────────────────


@pytest.mark.asyncio
async def test_job_match_inline_when_store_unavailable(
    client: AsyncClient, auth_headers: dict, resume_id: str, no_task_store
):
    with (
        patch(_ATS_PATCH, return_value=_fake_ats_obj()),
        patch(_SKILL_PATCH, return_value=_FAKE_SKILL_GAP),
        patch(_INTERVIEW_PATCH, return_value=_FAKE_QUESTIONS),
    ):
        resp = await _submit(client, auth_headers, resume_id)

    assert resp.status_code == 200
    assert set(resp.json().keys()) == {"ats", "skill_gap", "interview_questions"}


@pytest.mark.asyncio
async def test_job_match_inline_502_on_service_error(
    client: AsyncClient, auth_headers: dict, resume_id: str, no_task_store
):
    with (
        patch(_ATS_PATCH, side_effect=RuntimeError("model failed")),
        patch(_SKILL_PATCH, return_value=_FAKE_SKILL_GAP),
        patch(_INTERVIEW_PATCH, return_value=_FAKE_QUESTIONS),
    ):
        resp = await _submit(client, auth_headers, resume_id)
    assert resp.status_code == 502


# ── Input validation ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_job_match_accepts_empty_jd(
    client: AsyncClient, auth_headers: dict, resume_id: str, fake_task_store
):
    # Empty JD passes model validation (no min_length) — the task is still queued.
    with (
        patch(_ATS_PATCH, return_value=_fake_ats_obj()),
        patch(_SKILL_PATCH, return_value=_FAKE_SKILL_GAP),
        patch(_INTERVIEW_PATCH, return_value=_FAKE_QUESTIONS),
    ):
        resp = await client.post(
            "/api/v1/analysis/job-match",
            json={"resume_id": resume_id, "job_description": ""},
            headers=auth_headers,
        )
    assert resp.status_code == 202


@pytest.mark.asyncio
async def test_job_match_rejects_jd_exceeding_max_length(
    client: AsyncClient, auth_headers: dict, resume_id: str
):
    long_jd = "a" * 10_001
    resp = await client.post(
        "/api/v1/analysis/job-match",
        json={"resume_id": resume_id, "job_description": long_jd},
        headers=auth_headers,
    )
    assert resp.status_code == 422
