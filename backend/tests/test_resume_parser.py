"""
Real integration tests for the resume parser (ParsedResume schema).
Tests the service logic and Pydantic model validation — no LLM mocking.
"""

from app.services import resume_parser
from app.services.resume_parser import ParsedResume


def test_parsed_resume_defaults_are_safe():
    parsed = ParsedResume()
    assert parsed.full_name is None
    assert parsed.skills == []
    assert parsed.experience == []
    assert parsed.education == []
    assert parsed.projects == []
    assert parsed.parse_failed is False


def test_parsed_resume_accepts_full_data():
    parsed = ParsedResume(
        full_name="Jane Doe",
        email="jane@example.com",
        phone="+1-555-123-4567",
        location="New York, NY",
        skills=["Python", "Machine Learning", "FastAPI"],
        programming_languages=["Python", "SQL"],
        frameworks=["FastAPI", "PyTorch"],
        tools=["Docker", "Git"],
        experience=[
            {
                "title": "ML Engineer",
                "company": "Tech Corp",
                "duration": "2 years",
                "description": "Built models",
            }
        ],
        education=[{"degree": "M.Sc ML", "institution": "NYU", "year": "2022", "gpa": "3.9"}],
        certifications=["AWS Solutions Architect"],
        projects=[
            {
                "name": "Sentiment Analyzer",
                "description": "NLP project",
                "tech_stack": ["Python", "NLTK"],
            }
        ],
    )
    assert parsed.full_name == "Jane Doe"
    assert "Python" in parsed.skills
    assert len(parsed.experience) == 1
    assert parsed.experience[0]["company"] == "Tech Corp"
    assert len(parsed.education) == 1
    assert parsed.certifications == ["AWS Solutions Architect"]
    assert parsed.projects[0]["name"] == "Sentiment Analyzer"


def test_parsed_resume_json_round_trip():
    """Verify serialization/deserialization works correctly."""
    original = ParsedResume(
        full_name="Bob Smith",
        skills=["Python", "Docker"],
        programming_languages=["Python"],
    )
    json_str = original.model_dump_json()
    restored = ParsedResume.model_validate_json(json_str)
    assert restored.full_name == "Bob Smith"
    assert restored.skills == ["Python", "Docker"]


def test_parsed_resume_model_dump():
    parsed = ParsedResume(full_name="Test", skills=["Python"])
    data = parsed.model_dump()
    assert "full_name" in data
    assert "skills" in data
    assert "programming_languages" in data
    assert data["full_name"] == "Test"


def test_parse_failure_sets_the_marker(monkeypatch):
    """An LLM/parse error must be visible, not a silently empty structure."""

    def boom():
        raise RuntimeError("model unavailable")

    monkeypatch.setattr(resume_parser, "_build_llm", boom)
    parsed = resume_parser.parse_resume("Some resume text")
    assert parsed.parse_failed is True
    assert parsed.skills == []  # shape stays safe for consumers


def test_successful_parse_carries_no_marker(monkeypatch):
    from langchain_core.runnables import RunnableLambda

    fake_llm = RunnableLambda(lambda _prompt: '{"full_name": "Jane Doe", "skills": ["Python"]}')
    monkeypatch.setattr(resume_parser, "_build_llm", lambda: fake_llm)
    parsed = resume_parser.parse_resume("Jane Doe — Python developer")
    assert parsed.parse_failed is False
    assert parsed.full_name == "Jane Doe"
    assert parsed.skills == ["Python"]
