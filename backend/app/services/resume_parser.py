"""Parse resume text into structured data using the active LLM backend."""

import json
import logging
import re

from app.services.llm_schemas import ResumeExtraction

logger = logging.getLogger(__name__)


class ParsedResume(ResumeExtraction):
    """Stored parse result: the extracted fields plus the app-side failure marker."""

    # Not extracted from the resume: set when the parse itself errored, so the
    # API/UI can tell "parsing failed" apart from a genuinely empty result.
    parse_failed: bool = False


_PARSE_SYSTEM_PROMPT = (
    "You are an expert resume parser. Extract structured information from the "
    "resume text the user provides. Report only facts present in the text — "
    "use null or empty lists for anything missing; never invent data."
)

_PARSE_PROMPT_TEMPLATE = """You are an expert resume parser. Extract structured information from the resume text below.
Return ONLY a valid JSON object matching this exact schema. Do not include explanations.

Schema:
{{
  "full_name": "string or null",
  "email": "string or null",
  "phone": "string or null",
  "location": "string or null",
  "linkedin_url": "string or null",
  "github_url": "string or null",
  "summary": "string or null",
  "skills": ["list of all technical and soft skills"],
  "programming_languages": ["Python", "JavaScript", ...],
  "frameworks": ["FastAPI", "React", ...],
  "tools": ["Docker", "Git", ...],
  "experience": [{{"title": "...", "company": "...", "duration": "...", "description": "..."}}],
  "education": [{{"degree": "...", "institution": "...", "year": "...", "gpa": "..."}}],
  "certifications": ["list of certifications"],
  "projects": [{{"name": "...", "description": "...", "tech_stack": ["..."]}}]
}}

Resume Text:
{{resume_text}}

JSON Output:"""


def _build_llm():
    from app.core.config import settings  # noqa: PLC0415

    if settings.USE_GROQ:
        from langchain_groq import ChatGroq  # noqa: PLC0415

        logger.info("Using Groq API for resume parsing")
        return ChatGroq(
            model=settings.GROQ_LLM_MODEL,
            api_key=settings.GROQ_API_KEY,
            temperature=0,
        )
    else:
        from langchain_ollama import OllamaLLM  # noqa: PLC0415

        logger.info("Using Ollama for resume parsing")
        return OllamaLLM(
            model=settings.OLLAMA_LLM_MODEL,
            base_url=settings.OLLAMA_BASE_URL,
        )


def _parse_via_instructor(raw_text: str) -> ParsedResume:
    """Groq path: schema-validated extraction through the shared instructor client."""
    from app.services.llm_client import call_structured  # noqa: PLC0415

    extraction = call_structured(
        response_model=ResumeExtraction,
        system_prompt=_PARSE_SYSTEM_PROMPT,
        user_prompt=raw_text[:4000],
        temperature=0.0,
    )
    return ParsedResume(**extraction.model_dump())


def _parse_via_langchain(raw_text: str) -> ParsedResume:
    """Legacy prompt-to-JSON path: Ollama's default, and the Groq fallback."""
    from langchain_core.prompts import PromptTemplate  # noqa: PLC0415

    prompt = PromptTemplate.from_template(_PARSE_PROMPT_TEMPLATE)
    llm = _build_llm()
    chain = prompt | llm

    result = chain.invoke({"resume_text": raw_text[:4000]})

    # ChatGroq returns an AIMessage; Ollama returns a string
    raw_output = result.content if hasattr(result, "content") else str(result)
    raw_output = raw_output.strip()

    # Strip markdown code fences if present (handles ```json, ```JSON, trailing whitespace)
    raw_output = re.sub(r"^```(?:json)?\s*\n?", "", raw_output, flags=re.IGNORECASE)
    raw_output = re.sub(r"\n?```\s*$", "", raw_output)

    data = json.loads(raw_output)
    return ParsedResume(**data)


def parse_resume(raw_text: str) -> ParsedResume:
    from app.core.config import settings  # noqa: PLC0415

    # This was the one Groq feature still doing manual json.loads on raw LLM
    # output — instructor first, then the legacy path as a second chance, and
    # only then the parse_failed marker.
    if settings.USE_GROQ:
        try:
            return _parse_via_instructor(raw_text)
        except Exception as e:
            logger.warning("instructor resume parse failed (%s) — trying the legacy path", e)
    try:
        return _parse_via_langchain(raw_text)
    except Exception as e:
        logger.warning("Resume parsing failed, marking the resume unparsed: %s", e)
        return ParsedResume(parse_failed=True)
