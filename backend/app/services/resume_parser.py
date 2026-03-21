"""
Resume Parser Service
Extracts structured information from raw resume text using Ollama LLM with Pydantic schema enforcement.
Langchain imports are lazy (inside functions) so this module is importable without langchain installed.
"""
import json
import logging
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


def parse_resume(raw_text: str) -> ParsedResume:
    """
    Parse a resume using the LLM and return a validated ParsedResume object.
    Falls back to an empty ParsedResume on any error.
    Langchain/settings imports are deferred so this module is importable without them.
    """
    # Lazy imports — only needed at runtime, not at import time
    from langchain_community.llms import Ollama  # noqa: PLC0415
    from langchain_core.prompts import PromptTemplate  # noqa: PLC0415
    from app.core.config import settings  # noqa: PLC0415

    try:
        prompt = PromptTemplate.from_template(_PARSE_PROMPT_TEMPLATE)
        llm = Ollama(
            model=settings.OLLAMA_LLM_MODEL,
            base_url=settings.OLLAMA_BASE_URL,
        )
        chain = prompt | llm
        raw_output = chain.invoke({"resume_text": raw_text[:4000]})  # Limit input tokens

        # Strip markdown fences if present
        raw_output = raw_output.strip()
        if raw_output.startswith("```"):
            raw_output = raw_output.split("```")[1]
            if raw_output.startswith("json"):
                raw_output = raw_output[4:]

        data = json.loads(raw_output)
        return ParsedResume(**data)
    except Exception as e:
        logger.warning(f"Resume parsing failed, returning empty structure: {e}")
        return ParsedResume()
