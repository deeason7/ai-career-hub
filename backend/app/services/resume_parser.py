"""Parse resume text into structured data using the active LLM backend."""

import json
import logging
import re

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class ParsedResume(BaseModel):
    """Structured output of a parsed resume."""

    full_name: str | None = None
    email: str | None = None
    phone: str | None = None
    location: str | None = None
    linkedin_url: str | None = None
    github_url: str | None = None
    summary: str | None = None
    skills: list[str] = Field(default_factory=list)
    programming_languages: list[str] = Field(default_factory=list)
    frameworks: list[str] = Field(default_factory=list)
    tools: list[str] = Field(default_factory=list)
    experience: list[dict] = Field(
        default_factory=list
    )  # [{title, company, duration, description}]
    education: list[dict] = Field(default_factory=list)  # [{degree, institution, year, gpa}]
    certifications: list[str] = Field(default_factory=list)
    projects: list[dict] = Field(default_factory=list)  # [{name, description, tech_stack}]
    # Not extracted from the resume: set when the parse itself errored, so the
    # API/UI can tell "parsing failed" apart from a genuinely empty result.
    parse_failed: bool = False


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
        from langchain_community.llms import Ollama  # noqa: PLC0415

        logger.info("Using Ollama for resume parsing")
        return Ollama(
            model=settings.OLLAMA_LLM_MODEL,
            base_url=settings.OLLAMA_BASE_URL,
        )


def parse_resume(raw_text: str) -> ParsedResume:
    from langchain_core.prompts import PromptTemplate  # noqa: PLC0415

    try:
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
    except Exception as e:
        logger.warning("Resume parsing failed, marking the resume unparsed: %s", e)
        return ParsedResume(parse_failed=True)
