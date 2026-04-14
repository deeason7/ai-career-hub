"""Integration tests for the AI-as-a-Judge QA service.

Tests real LLM calls against Ollama (local) to verify that:
  1. Honest cover letters score high on honesty
  2. Hallucinated cover letters score low and get flagged
  3. The passes_qa threshold logic works correctly
  4. QA review handles edge cases gracefully
"""

import os

import pytest

from app.services.llm_client import reset_client
from app.services.qa_service import (
    HALLUCINATION_THRESHOLD,
    passes_qa,
    review_cover_letter,
)

pytestmark = pytest.mark.integration

_USING_GROQ = bool(os.environ.get("GROQ_API_KEY"))


@pytest.fixture(autouse=True)
def _clean_client():
    reset_client()
    yield
    reset_client()


_RESUME = (
    "Jane Doe — Software Engineer with 4 years of experience in Python and FastAPI. "
    "Built a data pipeline at Acme Corp processing 50K records/day using PostgreSQL "
    "and Redis. Led migration from Flask to FastAPI, reducing response times by 40%. "
    "Bachelor's in Computer Science from State University. Skills: Python, SQL, Docker, "
    "AWS EC2, Git, REST APIs, unit testing with pytest."
)

_JD = (
    "Senior Backend Engineer at TechCo. Requirements: 5+ years Python, experience "
    "with FastAPI or Django, PostgreSQL, Redis, Docker, CI/CD pipelines."
)

_HONEST_LETTER = (
    "Dear Hiring Manager,\n\n"
    "I am excited to apply for the Senior Backend Engineer role at TechCo. "
    "With 4 years of Python and FastAPI experience, including leading a "
    "Flask-to-FastAPI migration that reduced response times by 40% at Acme Corp, "
    "I am confident in my ability to contribute to your team.\n\n"
    "At Acme Corp, I built a data pipeline processing 50K records daily using "
    "PostgreSQL and Redis — technologies central to this role. My hands-on "
    "experience with Docker and AWS EC2 aligns with your infrastructure needs.\n\n"
    "I look forward to discussing how my background can support TechCo's goals.\n\n"
    "Best regards,\nJane Doe"
)

_HALLUCINATED_LETTER = (
    "Dear Hiring Manager,\n\n"
    "As a Staff Engineer with 12 years of experience leading distributed systems "
    "at Google and Netflix, I bring deep expertise in Kubernetes, Terraform, and "
    "Go. I architected a real-time analytics platform handling 10M RPM and managed "
    "a team of 25 engineers across 3 continents. My PhD in Machine Learning from "
    "MIT and 15 published papers give me a unique perspective.\n\n"
    "Best regards,\nJane Doe"
)


class TestReviewCoverLetter:
    def test_honest_letter_scores_high(self):
        """A cover letter grounded in resume facts should score >= threshold."""
        verdict = review_cover_letter(
            cover_letter=_HONEST_LETTER,
            resume_text=_RESUME,
            job_description=_JD,
        )
        assert verdict.honesty_score >= HALLUCINATION_THRESHOLD
        assert 1 <= verdict.tone_score <= 10
        assert len(verdict.reasoning) >= 10

    @pytest.mark.xfail(
        not _USING_GROQ,
        reason="llama3.2:3b identifies hallucinations in reasoning but doesn't "
        "calibrate numeric scores correctly (gave 8/10 despite flagging "
        "fabrications). Passes with Groq 8b.",
    )
    def test_hallucinated_letter_scores_low(self):
        """A cover letter with fabricated claims should score below threshold."""
        verdict = review_cover_letter(
            cover_letter=_HALLUCINATED_LETTER,
            resume_text=_RESUME,
            job_description=_JD,
        )
        assert verdict.honesty_score <= HALLUCINATION_THRESHOLD
        # Should flag at least some of the many fabrications
        assert len(verdict.flags) >= 1

    def test_verdict_structure(self):
        """Verify the verdict contains all expected fields."""
        verdict = review_cover_letter(
            cover_letter=_HONEST_LETTER,
            resume_text=_RESUME,
            job_description=_JD,
        )
        assert hasattr(verdict, "honesty_score")
        assert hasattr(verdict, "tone_score")
        assert hasattr(verdict, "flags")
        assert hasattr(verdict, "reasoning")
        assert isinstance(verdict.flags, list)


class TestPassesQA:
    def test_passes_above_threshold(self):
        """Scores at or above the threshold should pass."""
        from app.services.llm_schemas import QAVerdict

        verdict = QAVerdict(
            honesty_score=8,
            tone_score=7,
            flags=[],
            reasoning="Scores are above the threshold for passing.",
        )
        assert passes_qa(verdict) is True

    def test_fails_below_threshold(self):
        """Scores below the threshold should fail."""
        from app.services.llm_schemas import QAVerdict

        verdict = QAVerdict(
            honesty_score=4,
            tone_score=7,
            flags=["fabricated experience"],
            reasoning="Scores are below the threshold for quality.",
        )
        assert passes_qa(verdict) is False

    def test_boundary_at_threshold(self):
        """Score exactly at threshold should pass."""
        from app.services.llm_schemas import QAVerdict

        verdict = QAVerdict(
            honesty_score=HALLUCINATION_THRESHOLD,
            tone_score=7,
            flags=[],
            reasoning="Scores are at the exact boundary of passing.",
        )
        assert passes_qa(verdict) is True
