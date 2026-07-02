"""Job tracker automation: metadata extraction from job description text."""

import logging

logger = logging.getLogger(__name__)

_EXTRACT_SYSTEM_PROMPT = (
    "You are a precise data extractor. Read the job posting and return the company name "
    "and job title/role exactly as they appear. If either is not clearly stated, "
    'return "Unknown Company" or "Unknown Role" respectively.'
)


def extract_job_metadata(job_description: str) -> dict:
    """Extract company name and role from a job description.

    Returns {"company": str, "role": str}. Falls back to "Unknown" values on any failure.
    """
    from app.core.config import settings  # noqa: PLC0415

    fallback = {"company": "Unknown Company", "role": "Unknown Role"}
    jd_snippet = job_description[:3000]

    if settings.USE_GROQ:
        return _extract_via_instructor(jd_snippet, fallback)
    return _extract_via_langchain(jd_snippet, fallback)


def _extract_via_instructor(jd_snippet: str, fallback: dict) -> dict:
    from pydantic import ValidationError  # noqa: PLC0415

    from app.services.llm_client import call_structured  # noqa: PLC0415
    from app.services.llm_schemas import JobExtraction  # noqa: PLC0415

    try:
        result = call_structured(
            response_model=JobExtraction,
            system_prompt=_EXTRACT_SYSTEM_PROMPT,
            user_prompt=f"Job posting:\n{jd_snippet}\n\nExtract company and job title.",
            temperature=0.0,
        )
        return {
            "company": result.company or fallback["company"],
            "role": result.title or fallback["role"],
        }
    except (ValidationError, Exception) as exc:
        logger.warning("extract_job_metadata (instructor) failed: %s", exc)
        return fallback


def _extract_via_langchain(jd_snippet: str, fallback: dict) -> dict:
    try:
        from langchain_core.prompts import PromptTemplate  # noqa: PLC0415
        from langchain_ollama import OllamaLLM  # noqa: PLC0415

        from app.core.config import settings  # noqa: PLC0415

        llm = OllamaLLM(model=settings.OLLAMA_LLM_MODEL, base_url=settings.OLLAMA_BASE_URL)
        prompt = PromptTemplate.from_template(
            "Extract the company name and job title from this posting.\n"
            "Reply with exactly two lines:\n"
            "Company: <name>\n"
            "Role: <title>\n\n"
            "Posting:\n{jd}"
        )
        raw = (prompt | llm).invoke({"jd": jd_snippet})
        text = raw.content if hasattr(raw, "content") else str(raw)

        company, role = fallback["company"], fallback["role"]
        for line in text.splitlines():
            if line.lower().startswith("company:"):
                company = line.split(":", 1)[1].strip() or company
            elif line.lower().startswith("role:"):
                role = line.split(":", 1)[1].strip() or role
        return {"company": company, "role": role}
    except Exception as exc:
        logger.warning("extract_job_metadata (langchain) failed: %s", exc)
        return fallback
