"""Tests for LLM output schemas (Pydantic v2 validation contracts).

Verifies that the schemas enforce the constraints we rely on to prevent
bad LLM output from reaching the database or frontend.  No LLM calls —
these are pure unit tests on the Pydantic models.
"""
import pytest
from pydantic import ValidationError

from app.services.llm_schemas import (
    CoverLetterOutput,
    InterviewQuestions,
    JobExtraction,
    QAVerdict,
    SkillGapResult,
    SkillRecommendation,
)


class TestCoverLetterOutput:

    def test_valid_cover_letter(self):
        text = "A" * 250
        result = CoverLetterOutput(cover_letter=text)
        assert result.cover_letter == text

    def test_rejects_short_cover_letter(self):
        with pytest.raises(ValidationError, match="String should have at least 200 characters"):
            CoverLetterOutput(cover_letter="Too short")

    def test_rejects_empty_cover_letter(self):
        with pytest.raises(ValidationError):
            CoverLetterOutput(cover_letter="")


class TestQAVerdict:

    def test_valid_verdict(self):
        v = QAVerdict(
            honesty_score=8,
            tone_score=7,
            flags=["minor tone issue"],
            reasoning="The letter accurately reflects resume content.",
        )
        assert v.honesty_score == 8
        assert v.tone_score == 7
        assert len(v.flags) == 1

    def test_score_boundary_low(self):
        v = QAVerdict(honesty_score=1, tone_score=1, reasoning="Poor quality across the board.")
        assert v.honesty_score == 1

    def test_score_boundary_high(self):
        v = QAVerdict(honesty_score=10, tone_score=10, reasoning="Perfect letter. Grounded in facts.")
        assert v.honesty_score == 10

    def test_rejects_score_above_10(self):
        with pytest.raises(ValidationError, match="less than or equal to 10"):
            QAVerdict(honesty_score=11, tone_score=7, reasoning="Invalid score.")

    def test_rejects_score_below_1(self):
        with pytest.raises(ValidationError, match="greater than or equal to 1"):
            QAVerdict(honesty_score=0, tone_score=7, reasoning="Invalid score.")

    def test_rejects_short_reasoning(self):
        with pytest.raises(ValidationError, match="at least 10 characters"):
            QAVerdict(honesty_score=8, tone_score=7, reasoning="Short")

    def test_empty_flags_default(self):
        v = QAVerdict(honesty_score=9, tone_score=9, reasoning="Clean letter, no issues found.")
        assert v.flags == []


class TestInterviewQuestions:

    def test_valid_questions(self):
        qs = [f"Question {i}?" for i in range(10)]
        result = InterviewQuestions(questions=qs)
        assert len(result.questions) == 10

    def test_minimum_questions(self):
        qs = [f"Question {i}?" for i in range(5)]
        result = InterviewQuestions(questions=qs)
        assert len(result.questions) == 5

    def test_rejects_too_few_questions(self):
        with pytest.raises(ValidationError, match="at least 5"):
            InterviewQuestions(questions=["Q1?", "Q2?", "Q3?"])

    def test_rejects_too_many_questions(self):
        qs = [f"Question {i}?" for i in range(20)]
        with pytest.raises(ValidationError, match="at most 15"):
            InterviewQuestions(questions=qs)


class TestSkillGapResult:

    def test_valid_result(self):
        rec = SkillRecommendation(
            skill="Kubernetes",
            resource="CKA on Linux Foundation",
            timeline="6 weeks",
        )
        result = SkillGapResult(
            missing_skills=["Kubernetes", "Terraform"],
            priority_gaps=["Kubernetes"],
            recommendations=[rec],
        )
        assert len(result.missing_skills) == 2
        assert result.recommendations[0].skill == "Kubernetes"

    def test_empty_defaults(self):
        result = SkillGapResult()
        assert result.missing_skills == []
        assert result.priority_gaps == []
        assert result.recommendations == []


class TestJobExtraction:

    def test_valid_extraction(self):
        je = JobExtraction(
            title="Senior Backend Engineer",
            company="Acme Corp",
            required_skills=["Python", "PostgreSQL"],
            preferred_skills=["Kubernetes"],
            experience_level="senior",
            description_summary="Build scalable APIs for the Acme platform.",
        )
        assert je.title == "Senior Backend Engineer"
        assert len(je.required_skills) == 2

    def test_defaults(self):
        je = JobExtraction(
            title="Engineer",
            description_summary="A role at a company.",
        )
        assert je.company == ""
        assert je.experience_level == "not specified"
        assert je.required_skills == []

    def test_rejects_oversized_summary(self):
        with pytest.raises(ValidationError, match="at most 500"):
            JobExtraction(
                title="Engineer",
                description_summary="X" * 501,
            )
