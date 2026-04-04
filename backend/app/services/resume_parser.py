"""
Resume Parser Service

Extracts structured information from raw resume text using an LLM.
Auto-detects: uses Groq (free cloud API) if GROQ_API_KEY is set, otherwise falls back to Ollama (local).
All heavy imports are lazy so this module is importable without langchain installed.
"""
import json
import logging
import re
from typing import Optional

from pydantic import BaseModel

logger = logging.getLogger(__name__)


class ParsedResume(BaseModel):
    """Structured output of a parsed resume."""
    full_name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    location: Optional[str] = None
    linkedin_url: Optional[str] = None
    github_url: Optional[str] = None
    summary: Optional[str] = None
    skills: list[str] = []
    programming_languages: list[str] = []
    frameworks: list[str] = []
    tools: list[str] = []
    experience: list[dict] = []   # [{title, company, duration, description}]
    education: list[dict] = []    # [{degree, institution, year, gpa}]
    certifications: list[str] = []
    projects: list[dict] = []     # [{name, description, tech_stack}]


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
    """
    Build the LLM client based on available configuration.
    Priority: Groq (free cloud) > Ollama (local)
    """
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
    """
    Parse a resume using LLM (Groq or Ollama) and return a validated ParsedResume.
    Falls back to an empty ParsedResume on any error.
    """
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
        logger.warning("Resume parsing failed, returning empty structure: %s", e)
        return ParsedResume()
