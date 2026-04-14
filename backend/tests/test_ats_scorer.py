"""
Real integration tests for the ATS Scorer service.
No mocks — tests the actual algorithmic scoring logic.
"""

from app.services.ats_scorer import ATSResult, calculate_ats_score

SAMPLE_RESUME = """
SUMMARY
Experienced Python developer with 4 years of experience building scalable REST APIs.

SKILLS
Python, FastAPI, Django, PostgreSQL, Docker, Redis, Git, CI/CD, AWS

EXPERIENCE
Senior Backend Engineer — Acme Corp (2022 – Present)
- Built microservices using FastAPI and PostgreSQL, improving API response time by 40%
- Deployed containerized applications using Docker and Kubernetes on AWS

EDUCATION
B.Sc Computer Science — State University, 2021

PROJECTS
AI Resume Analyzer — Python, FastAPI, LangChain, FAISS
"""

JD_MATCHING = """
We are looking for a Python Backend Engineer with experience in FastAPI, PostgreSQL, Docker, and AWS.
Knowledge of CI/CD pipelines and Redis is a plus. You will build microservices and REST APIs.
"""

JD_NO_MATCH = """
We are looking for a Java Spring Boot developer with Oracle Database experience.
Knowledge of Hibernate, Maven, and JEE is required. React frontend skills also needed.
"""


def test_ats_score_returns_result_object():
    result = calculate_ats_score(SAMPLE_RESUME, JD_MATCHING)
    assert isinstance(result, ATSResult)


def test_high_match_produces_good_score():
    result = calculate_ats_score(SAMPLE_RESUME, JD_MATCHING)
    assert result.score >= 50, f"Expected score >= 50 for good match, got {result.score}"


def test_low_match_produces_low_score():
    result = calculate_ats_score(SAMPLE_RESUME, JD_NO_MATCH)
    assert result.score < 50, f"Expected score < 50 for poor match, got {result.score}"


def test_matched_keywords_not_empty_for_good_match():
    result = calculate_ats_score(SAMPLE_RESUME, JD_MATCHING)
    assert len(result.matched_keywords) > 0


def test_python_found_in_matched():
    result = calculate_ats_score(SAMPLE_RESUME, JD_MATCHING)
    assert "python" in result.matched_keywords


def test_missing_keywords_for_no_match():
    result = calculate_ats_score(SAMPLE_RESUME, JD_NO_MATCH)
    assert len(result.missing_keywords) > 0


def test_score_is_clamped_between_0_and_100():
    result = calculate_ats_score(SAMPLE_RESUME, JD_MATCHING)
    assert 0 <= result.score <= 100


def test_breakdown_structure():
    result = calculate_ats_score(SAMPLE_RESUME, JD_MATCHING)
    assert "keyword_score" in result.breakdown
    assert "structure_score" in result.breakdown
    assert "matched_count" in result.breakdown


def test_structure_score_for_complete_resume():
    result = calculate_ats_score(SAMPLE_RESUME, JD_MATCHING)
    assert result.structure_score > 50, "Complete resume should score well on structure"


def test_structure_score_for_empty_resume():
    result = calculate_ats_score("John Doe\njohn@example.com", JD_MATCHING)
    assert result.structure_score < 50, "Bare resume should score low on structure"


def test_recommendations_provided_when_gaps_exist():
    result = calculate_ats_score(SAMPLE_RESUME, JD_NO_MATCH)
    assert len(result.recommendations) > 0
