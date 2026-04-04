"""
Cover Letter Generator Service

Two execution paths based on environment:
  - Groq (cloud/free): sends full resume text directly — uses 128K context window, no FAISS needed
  - Ollama (local dev): uses RAG pipeline with FAISS for context retrieval

Zero-hallucination: only uses facts from the candidate's actual resume.
"""
import logging

from langchain_core.prompts import PromptTemplate

logger = logging.getLogger(__name__)

# Resumes are typically 2–5 K chars; 6 K is generous while well within Groq's 128 K token window.
_GROQ_RESUME_MAX_CHARS = 6_000

_COVER_LETTER_PROMPT = PromptTemplate.from_template(
    """You are a professional career coach. Write a compelling, honest, and tailored cover letter.

STRICT RULE: Use ONLY the verified facts below. Never invent metrics, skills, or experiences.
If the resume facts don't match the job requirements, acknowledge the candidate's strengths
in related areas without fabricating experience.

=== VERIFIED CANDIDATE FACTS (from resume) ===
{context}

=== JOB DESCRIPTION ===
{job_description}

=== COVER LETTER STRUCTURE ===
Paragraph 1 (Hook): Why this role excites the candidate + strongest matching credential.
Paragraph 2 (Evidence): 2-3 specific achievements from the verified facts above that match the JD.
Paragraph 3 (Fit): Cultural/team fit + what the candidate will contribute.
Closing: Professional sign-off requesting an interview.

Write the full cover letter below (no metadata, no placeholders):
"""
)


def _build_llm():
    """
    Return the appropriate LLM client.
    Groq is preferred (free, fast, 128K context). Falls back to Ollama for local dev.
    """
    from app.core.config import settings  # noqa: PLC0415

    if settings.USE_GROQ:
        from langchain_groq import ChatGroq  # noqa: PLC0415
        logger.info("LLM backend: Groq (%s)", settings.GROQ_LLM_MODEL)
        return ChatGroq(
            model=settings.GROQ_LLM_MODEL,
            api_key=settings.GROQ_API_KEY,
            temperature=0.3,
        )
    else:
        from langchain_community.llms import Ollama  # noqa: PLC0415
        logger.info("LLM backend: Ollama (%s)", settings.OLLAMA_LLM_MODEL)
        return Ollama(
            model=settings.OLLAMA_LLM_MODEL,
            base_url=settings.OLLAMA_BASE_URL,
        )


def _extract_text(result) -> str:
    """Handle both AIMessage (ChatGroq) and str (Ollama) responses."""
    return result.content if hasattr(result, "content") else str(result)


def _rag_retrieve(resume_text: str, job_description: str) -> tuple[str, int]:
    """
    FAISS-based RAG retrieval for Ollama path.
    Returns (context_string, chunks_used).
    """
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


def generate_cover_letter(resume_text: str, job_description: str) -> dict:
    """
    Generate a zero-hallucination cover letter.
    - Groq path: sends full resume (128K context window) directly — no FAISS needed
    - Ollama path: uses RAG to retrieve top-6 relevant chunks via FAISS
    """
    from app.core.config import settings  # noqa: PLC0415

    if settings.USE_GROQ:
        context = resume_text[:_GROQ_RESUME_MAX_CHARS]
        chunks_used = 1
    else:
        context, chunks_used = _rag_retrieve(resume_text, job_description)

    llm = _build_llm()
    chain = _COVER_LETTER_PROMPT | llm
    result = chain.invoke({"context": context, "job_description": job_description})
    cover_letter = _extract_text(result).strip()

    return {
        "cover_letter": cover_letter,
        "rag_context": context[:500] + "..." if len(context) > 500 else context,
        "chunks_used": chunks_used,
    }


def generate_skill_gap_analysis(resume_text: str, job_description: str) -> dict:
    """Identify missing skills and generate prioritised learning recommendations."""
    from app.services.ats_scorer import PRIORITY_KEYWORDS, calculate_ats_score  # noqa: PLC0415

    ats = calculate_ats_score(resume_text, job_description)
    missing = ats.missing_keywords[:15]
    priority_gaps = [kw for kw in missing if kw in PRIORITY_KEYWORDS][:5]

    recommendations = []
    if priority_gaps:
        llm = _build_llm()
        prompt = PromptTemplate.from_template(
            "For a job seeker missing these skills: {skills}\n"
            "Give 3 specific, actionable learning recommendations (course name, platform, timeline).\n"
            "Be concise. Format as a numbered list."
        )
        result = (prompt | llm).invoke({"skills": ", ".join(priority_gaps)})
        recs_text = _extract_text(result).strip()
        recommendations = [r.strip() for r in recs_text.split("\n") if r.strip()]

    return {
        "ats_score": ats.score,
        "matched_skills": ats.matched_keywords[:20],
        "missing_skills": missing,
        "priority_gaps": priority_gaps,
        "learning_recommendations": recommendations,
    }


def generate_interview_questions(resume_text: str, job_description: str) -> list[str]:
    """Generate 10 tailored interview questions based on the JD and resume."""
    llm = _build_llm()
    prompt = PromptTemplate.from_template(
        "You are a senior technical interviewer. Based on this job description and candidate resume, "
        "generate exactly 10 highly specific interview questions. "
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
    output = _extract_text(result).strip()
    lines = [line.strip() for line in output.split("\n") if line.strip()]
    questions = [line for line in lines if line[0].isdigit() or line.startswith("-")]
    return questions[:10] if questions else [output]
