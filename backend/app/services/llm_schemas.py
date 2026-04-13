"""Pydantic v2 contracts for all LLM-generated outputs.

Every structured response from Groq/LLaMA passes through one of these models
before reaching application code.  instructor handles the parsing and retry
logic; these schemas define what "valid" looks like.

Design note: Field constraints (ge, le, min_length) act as compile-time
guarantees — if the LLM hallucinates a score of 15 or returns an empty
cover letter, validation fails *before* we persist anything to the DB.

Keep docstrings and field descriptions minimal — smaller models (3b) echo
verbose descriptions back as part of the JSON structure instead of filling
in the actual data.
"""
from pydantic import BaseModel, Field


class CoverLetterOutput(BaseModel):
    """Generated cover letter."""
    cover_letter: str = Field(..., min_length=200)


class QAVerdict(BaseModel):
    """QA review scores for a cover letter."""
    honesty_score: int = Field(..., ge=1, le=10)
    tone_score: int = Field(..., ge=1, le=10)
    flags: list[str] = Field(default_factory=list)
    reasoning: str = Field(..., min_length=10)


class InterviewQuestions(BaseModel):
    """List of interview questions."""
    questions: list[str] = Field(..., min_length=5, max_length=15)


class SkillRecommendation(BaseModel):
    """A single learning recommendation."""
    skill: str
    resource: str
    timeline: str


class SkillGapResult(BaseModel):
    """Skill gap analysis output."""
    missing_skills: list[str] = Field(default_factory=list)
    priority_gaps: list[str] = Field(default_factory=list)
    recommendations: list[SkillRecommendation] = Field(default_factory=list)


class JobExtraction(BaseModel):
    """Structured data extracted from a job description."""
    title: str
    company: str = Field(default="")
    required_skills: list[str] = Field(default_factory=list)
    preferred_skills: list[str] = Field(default_factory=list)
    experience_level: str = Field(default="not specified")
    description_summary: str = Field(..., max_length=500)
