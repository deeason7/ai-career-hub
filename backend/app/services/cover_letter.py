"""Cover Letter Generator + AI Tools Service

Two execution paths based on environment:
  - Groq (cloud): structured output via instructor — validated Pydantic models
  - Ollama (local dev): LangChain RAG pipeline with FAISS context retrieval

The Groq path uses the dedicated llm_client for structured output.
The Ollama path keeps the LangChain chain for local dev compatibility.
"""
import logging

from pydantic import ValidationError

logger = logging.getLogger(__name__)

# Resumes are typically 2–5 K chars; 6 K is generous while well within Groq's 128 K token window.
_GROQ_RESUME_MAX_CHARS = 6_000

_COVER_LETTER_SYSTEM_PROMPT = (
    "You are a professional career coach. Write a compelling, honest, "
    "and tailored cover letter.\n\n"
    "STRICT RULE: Use ONLY the verified facts provided. Never invent metrics, "
    "skills, or experiences. If the resume facts don't match the job requirements, "
    "acknowledge the candidate's strengths in related areas without fabricating experience.\n\n"
    "COVER LETTER STRUCTURE:\n"
    "Paragraph 1 (Hook): Why this role excites the candidate + strongest matching credential.\n"
    "Paragraph 2 (Evidence): 2-3 specific achievements from the resume that match the JD.\n"
    "Paragraph 3 (Fit): Cultural/team fit + what the candidate will contribute.\n"
    "Closing: Professional sign-off requesting an interview."
)

_INTERVIEW_SYSTEM_PROMPT = (
    "You are a senior technical interviewer. Generate highly specific interview "
    "questions based on the provided job description and candidate resume. "
    "Mix behavioral (STAR format), technical, and situational questions."
)

_SKILL_GAP_SYSTEM_PROMPT = (
    "You are a career development advisor. For a job seeker missing certain skills, "
    "provide specific, actionable learning recommendations. Include the skill name, "
    "a concrete resource (course name and platform), and a realistic timeline."
)


def _build_ollama_llm():
    """Return an Ollama LLM client for local dev. Not used when Groq is configured."""
    from langchain_community.llms import Ollama  # noqa: PLC0415

    from app.core.config import settings  # noqa: PLC0415

    logger.info("LLM backend: Ollama (%s)", settings.OLLAMA_LLM_MODEL)
    return Ollama(
        model=settings.OLLAMA_LLM_MODEL,
        base_url=settings.OLLAMA_BASE_URL,
    )


def _rag_retrieve(resume_text: str, job_description: str) -> tuple[str, int]:
    """FAISS-based RAG retrieval for Ollama path. Returns (context, chunks_used)."""
    from langchain_community.embeddings import OllamaEmbeddings  # noqa: PLC0415
    from langchain_community.vectorstores import FAISS  # noqa: PLC0415
    from langchain_core.documents import Document  # noqa: PLC0415
    from langchain_text_splitters import RecursiveCharacterTextSplitter  # noqa: PLC0415

    from app.core.config import settings  # noqa: PLC0415

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=400, chunk_overlap=60,
        separators=["\n\n", "\n", ".", " ", ""],
    )
    docs = [Document(page_content=chunk) for chunk in splitter.split_text(resume_text)]

    embeddings = OllamaEmbeddings(
        model=settings.OLLAMA_EMBED_MODEL,
        base_url=settings.OLLAMA_BASE_URL,
    )
    vectorstore = FAISS.from_documents(docs, embeddings)
    relevant_docs = vectorstore.as_retriever(search_kwargs={"k": 6}).invoke(job_description)
    context = "\n\n---\n\n".join(doc.page_content for doc in relevant_docs)
    return context, len(relevant_docs)


def _generate_via_ollama(resume_text: str, job_description: str) -> dict:
    """Ollama path: LangChain RAG pipeline with FAISS retrieval."""
    from langchain_core.prompts import PromptTemplate  # noqa: PLC0415

    context, chunks_used = _rag_retrieve(resume_text, job_description)
    llm = _build_ollama_llm()
    prompt = PromptTemplate.from_template(
        _COVER_LETTER_SYSTEM_PROMPT + "\n\n"
        "=== VERIFIED CANDIDATE FACTS (from resume) ===\n{context}\n\n"
        "=== JOB DESCRIPTION ===\n{job_description}\n\n"
        "Write the full cover letter below (no metadata, no placeholders):\n"
    )
    chain = prompt | llm
    result = chain.invoke({"context": context, "job_description": job_description})
    text = result.content if hasattr(result, "content") else str(result)

    return {
        "cover_letter": text.strip(),
        "rag_context": context[:500] + "..." if len(context) > 500 else context,
        "chunks_used": chunks_used,
    }


def generate_cover_letter(resume_text: str, job_description: str) -> dict:
    """Generate a cover letter grounded in resume facts.

    Groq path: uses instructor for validated structured output.
    Ollama path: falls back to LangChain RAG pipeline.
    """
    from app.core.config import settings  # noqa: PLC0415

    if not settings.USE_GROQ:
        return _generate_via_ollama(resume_text, job_description)

    from app.services.llm_client import call_structured  # noqa: PLC0415
    from app.services.llm_schemas import CoverLetterOutput  # noqa: PLC0415

    context = resume_text[:_GROQ_RESUME_MAX_CHARS]
    user_prompt = (
        f"=== VERIFIED CANDIDATE FACTS (from resume) ===\n{context}\n\n"
        f"=== JOB DESCRIPTION ===\n{job_description}\n\n"
        "Write the full cover letter. No metadata, no placeholders."
    )

    try:
        result = call_structured(
            response_model=CoverLetterOutput,
            system_prompt=_COVER_LETTER_SYSTEM_PROMPT,
            user_prompt=user_prompt,
        )
        return {
            "cover_letter": result.cover_letter,
            "rag_context": context[:500] + "..." if len(context) > 500 else context,
            "chunks_used": 1,
        }
    except ValidationError:
        logger.warning("Structured output failed validation, falling back to raw generation")
        return _generate_via_ollama(resume_text, job_description)


def generate_skill_gap_analysis(resume_text: str, job_description: str) -> dict:
    """Identify missing skills and generate prioritised learning recommendations."""
    from app.services.ats_scorer import PRIORITY_KEYWORDS, calculate_ats_score  # noqa: PLC0415

    ats = calculate_ats_score(resume_text, job_description)
    missing = ats.missing_keywords[:15]
    priority_gaps = [kw for kw in missing if kw in PRIORITY_KEYWORDS][:5]

    recommendations = []
    if priority_gaps:
        from app.core.config import settings  # noqa: PLC0415

        if settings.USE_GROQ:
            recommendations = _skill_gap_via_instructor(priority_gaps)
        else:
            recommendations = _skill_gap_via_langchain(priority_gaps)

    return {
        "ats_score": ats.score,
        "matched_skills": ats.matched_keywords[:20],
        "missing_skills": missing,
        "priority_gaps": priority_gaps,
        "learning_recommendations": recommendations,
    }


def _skill_gap_via_instructor(priority_gaps: list[str]) -> list[dict]:
    """Structured skill gap recommendations via instructor."""
    from app.services.llm_client import call_structured  # noqa: PLC0415
    from app.services.llm_schemas import SkillGapResult  # noqa: PLC0415

    user_prompt = (
        f"The candidate is missing these skills: {', '.join(priority_gaps)}\n"
        "Provide 3 specific, actionable learning recommendations."
    )
    try:
        result = call_structured(
            response_model=SkillGapResult,
            system_prompt=_SKILL_GAP_SYSTEM_PROMPT,
            user_prompt=user_prompt,
        )
        return [rec.model_dump() for rec in result.recommendations]
    except ValidationError:
        logger.warning("Skill gap structured output failed, falling back to LangChain")
        return _skill_gap_via_langchain(priority_gaps)


def _skill_gap_via_langchain(priority_gaps: list[str]) -> list[str]:
    """Fallback: unstructured skill gap recommendations via LangChain."""
    from langchain_core.prompts import PromptTemplate  # noqa: PLC0415

    llm = _build_ollama_llm()
    prompt = PromptTemplate.from_template(
        "For a job seeker missing these skills: {skills}\n"
        "Give 3 specific, actionable learning recommendations "
        "(course name, platform, timeline).\n"
        "Be concise. Format as a numbered list."
    )
    result = (prompt | llm).invoke({"skills": ", ".join(priority_gaps)})
    text = result.content if hasattr(result, "content") else str(result)
    return [r.strip() for r in text.strip().split("\n") if r.strip()]


def generate_interview_questions(resume_text: str, job_description: str) -> list[str]:
    """Generate tailored interview questions."""
    from app.core.config import settings  # noqa: PLC0415

    if settings.USE_GROQ:
        return _interview_via_instructor(resume_text, job_description)
    return _interview_via_langchain(resume_text, job_description)


def _interview_via_instructor(resume_text: str, job_description: str) -> list[str]:
    """Structured interview questions via instructor — no regex parsing needed."""
    from app.services.llm_client import call_structured  # noqa: PLC0415
    from app.services.llm_schemas import InterviewQuestions  # noqa: PLC0415

    user_prompt = (
        f"JOB DESCRIPTION:\n{job_description[:1500]}\n\n"
        f"CANDIDATE RESUME (excerpt):\n{resume_text[:1500]}\n\n"
        "Generate 10 highly specific interview questions."
    )
    try:
        result = call_structured(
            response_model=InterviewQuestions,
            system_prompt=_INTERVIEW_SYSTEM_PROMPT,
            user_prompt=user_prompt,
        )
        return result.questions[:10]
    except ValidationError:
        logger.warning("Interview questions structured output failed, falling back")
        return _interview_via_langchain(resume_text, job_description)


def _interview_via_langchain(resume_text: str, job_description: str) -> list[str]:
    """Fallback: unstructured interview questions via LangChain."""
    from langchain_core.prompts import PromptTemplate  # noqa: PLC0415

    llm = _build_ollama_llm()
    prompt = PromptTemplate.from_template(
        "You are a senior technical interviewer. Based on this job description "
        "and candidate resume, generate exactly 10 highly specific interview questions. "
        "Mix behavioral (STAR format), technical, and situational questions.\n\n"
        "JOB DESCRIPTION:\n{job_description}\n\n"
        "CANDIDATE RESUME (excerpt):\n{resume_excerpt}\n\n"
        "Output format: Numbered list 1-10. One question per line. No explanations.\n\n"
        "Interview Questions:"
    )
    result = (prompt | llm).invoke({
        "job_description": job_description[:1500],
        "resume_excerpt": resume_text[:1500],
    })
    output = result.content if hasattr(result, "content") else str(result)
    output = output.strip()
    lines = [line.strip() for line in output.split("\n") if line.strip()]
    questions = [line for line in lines if line[0].isdigit() or line.startswith("-")]
    return questions[:10] if questions else [output]
