"""Tests for the cover letter service dual-path fallback."""

from unittest.mock import patch

from pydantic import ValidationError

from app.services import cover_letter


def test_generate_falls_back_to_ollama_on_validation_error():
    """A Groq-path ValidationError must fall back to the Ollama/LangChain path."""
    sentinel = {"cover_letter": "fallback text", "chunks_used": 0}

    def _raise(*args, **kwargs):
        raise ValidationError.from_exception_data(title="CoverLetterOutput", line_errors=[])

    with (
        patch("app.core.config.settings") as mock_settings,
        patch("app.services.llm_client.call_structured", side_effect=_raise),
        patch(
            "app.services.cover_letter._generate_via_ollama", return_value=sentinel
        ) as mock_ollama,
    ):
        mock_settings.USE_GROQ = True
        result = cover_letter.generate_cover_letter(
            "Jane Doe, Python engineer with FastAPI experience.",
            "We are hiring a Python backend engineer with FastAPI and PostgreSQL.",
        )

    assert result == sentinel
    mock_ollama.assert_called_once()
