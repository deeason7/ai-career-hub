"""Tests for the AI tools endpoints — ATS score, skill gap, interview questions."""

import io
from unittest.mock import patch

import pytest
import pytest_asyncio
from httpx import AsyncClient

from app.services.ats_scorer import ATSResult

_ATS_PATCH = "app.api.v1.endpoints.ai_tools.calculate_ats_score"
_SKILL_PATCH = "app.api.v1.endpoints.ai_tools.generate_skill_gap_analysis"
_INTERVIEW_PATCH = "app.api.v1.endpoints.ai_tools.generate_interview_questions"

_FAKE_SKILL_GAP = {
    "ats_score": 70.0,
    "matched_skills": ["python"],
    "missing_skills": ["kubernetes"],
    "priority_gaps": ["kubernetes"],
    "learning_recommendations": [],
}
_FAKE_QUESTIONS = ["Tell me about your FastAPI experience.", "How do you handle async IO?"]


def _ats_result() -> ATSResult:
    return ATSResult(
        score=72.0,
        semantic_score=68.0,
        keyword_score=80.0,
        structure_score=60.0,
        matched_keywords=["python"],
        missing_keywords=["kubernetes"],
        recommendations=[],
        section_scores={},
        breakdown={},
    )


@pytest_asyncio.fixture
async def resume_id(client: AsyncClient, auth_headers: dict) -> str:
    content = b"Python developer with 3 years of FastAPI and PostgreSQL experience."
    resp = await client.post(
        "/api/v1/resumes/upload",
        files={"file": ("resume.txt", io.BytesIO(content), "text/plain")},
        data={"name": "AI Tools Resume"},
        headers=auth_headers,
    )
    assert resp.status_code == 201
    return resp.json()["id"]


@pytest.mark.asyncio
async def test_ats_score_returns_shape(client: AsyncClient, auth_headers: dict, resume_id: str):
    with patch(_ATS_PATCH, return_value=_ats_result()):
        resp = await client.post(
            "/api/v1/ai/ats-score",
            json={"job_description": "Python backend engineer role", "resume_id": resume_id},
            headers=auth_headers,
        )
    assert resp.status_code == 200
    assert resp.json()["score"] == 72.0


@pytest.mark.asyncio
async def test_skill_gap_offloaded(client: AsyncClient, auth_headers: dict, resume_id: str):
    with patch(_SKILL_PATCH, return_value=_FAKE_SKILL_GAP):
        resp = await client.post(
            "/api/v1/ai/skill-gap",
            json={"job_description": "Python backend engineer role", "resume_id": resume_id},
            headers=auth_headers,
        )
    assert resp.status_code == 200
    assert resp.json()["priority_gaps"] == ["kubernetes"]


@pytest.mark.asyncio
async def test_interview_questions_offloaded(
    client: AsyncClient, auth_headers: dict, resume_id: str
):
    with patch(_INTERVIEW_PATCH, return_value=_FAKE_QUESTIONS):
        resp = await client.post(
            "/api/v1/ai/interview-questions",
            json={"job_description": "Python backend engineer role", "resume_id": resume_id},
            headers=auth_headers,
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 2
    assert data["questions"] == _FAKE_QUESTIONS


@pytest.mark.asyncio
async def test_skill_gap_returns_502_on_service_error(
    client: AsyncClient, auth_headers: dict, resume_id: str
):
    with patch(_SKILL_PATCH, side_effect=RuntimeError("llm down")):
        resp = await client.post(
            "/api/v1/ai/skill-gap",
            json={"job_description": "Python backend engineer role", "resume_id": resume_id},
            headers=auth_headers,
        )
    assert resp.status_code == 502
