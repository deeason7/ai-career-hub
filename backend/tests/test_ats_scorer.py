"""Integration tests for the ATS scorer — real algorithmic scoring, no mocks."""

from app.core.utils import sanitize_text
from app.services.ats_scorer import (
    ATSResult,
    _is_keyword,
    _score_keywords,
    _strip_boilerplate,
    calculate_ats_score,
)

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


# ── Keyword quality: boilerplate, junk terms, shorthands ─────────────────────
# A realistic LinkedIn-style posting: real requirements wrapped in scrape noise,
# a benefits paragraph, and the standard EEO block.

LINKEDIN_STYLE_JD = """
Senior Machine Learning Engineer
Acme Group Group · New York, NY · via linkedin.com

About the role:
We're hiring a Senior Machine Learning Engineer to build NLP pipelines with Python,
PyTorch, and Kubernetes. You'll own CI/CD for model deployment and work with AWS.

What we offer:
Competitive salary and a comprehensive benefits package. Medical, dental, and vision
insurance. 401k matching, paid time off, and parental leave. Tuition reimbursement
is available alongside wellness perks.

Acme is an equal opportunity employer. All qualified applicants will receive
consideration for employment without regard to race, color, religion, gender,
sexual orientation, national origin, disability, age, or protected veteran status,
as applicable under federal law.
Reasonable accommodation is available for applicants with disabilities.
"""

KEYWORD_RESUME = (
    "Machine learning engineer. Skills: Python, PyTorch, Kubernetes, AWS, CI/CD, "
    "NLP pipelines, model deployment."
)


def _surfaced_keywords(jd: str) -> set[str]:
    _, matched, missing = _score_keywords(KEYWORD_RESUME, jd)
    return set(matched) | set(missing)


def test_eeo_terms_never_surface_as_keywords():
    surfaced = _surfaced_keywords(LINKEDIN_STYLE_JD)
    for junk in (
        "accommodation",
        "disability",
        "employer",
        "gender",
        "religion",
        "veteran",
        "applicable",
        "alongside",
    ):
        assert junk not in surfaced, f"EEO/filler term '{junk}' surfaced as a keyword"


def test_benefits_and_web_junk_never_surface():
    surfaced = _surfaced_keywords(LINKEDIN_STYLE_JD)
    for junk in ("benefits", "dental", "insurance", "tuition", "wellness", "com", "salary"):
        assert junk not in surfaced, f"benefits/web junk '{junk}' surfaced as a keyword"


def test_tech_terms_survive_the_cleanup():
    _, matched, _ = _score_keywords(KEYWORD_RESUME, LINKEDIN_STYLE_JD)
    for skill in ("python", "pytorch", "kubernetes", "aws", "nlp"):
        assert skill in matched, f"real skill '{skill}' was lost by the cleanup"
    assert "machine learning" in matched


def test_no_repeated_word_phrases():
    surfaced = _surfaced_keywords(LINKEDIN_STYLE_JD)
    stutters = [p for p in surfaced if " " in p and len(set(p.split())) == 1]
    assert stutters == [], f"repeated-word phrases surfaced: {stutters}"
    assert "group" not in surfaced  # "Acme Group Group" is a name, not a skill


def test_strip_survives_whitespace_collapse():
    # The request pipeline flattens newlines before the scorer runs — the EEO
    # block must still be dropped on sentence boundaries alone.
    flat = sanitize_text(LINKEDIN_STYLE_JD)
    assert "\n" not in flat
    surfaced = _surfaced_keywords(flat)
    assert "veteran" not in surfaced
    assert "dental" not in surfaced
    _, matched, _ = _score_keywords(KEYWORD_RESUME, flat)
    assert "python" in matched


def test_strip_never_empties_a_pure_boilerplate_jd():
    pure_eeo = (
        "We are an equal opportunity employer. All qualified applicants will receive consideration."
    )
    assert _strip_boilerplate(pure_eeo) == pure_eeo


def test_short_tech_shorthands_are_keywords():
    assert _is_keyword("ai") is True
    assert _is_keyword("ml") is True
    assert _is_keyword("ci") is True
    # Deliberately not whitelisted: lowercase "go"/"r" are ambiguous junk.
    assert _is_keyword("go") is False
    assert _is_keyword("xy") is False
