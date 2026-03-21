"""
Cover Letter Generator Service

Uses a RAG pipeline (FAISS + LLM) to generate honest, resume-grounded cover letters.
Zero-hallucination: only uses facts retrieved from the candidate's actual resume.

LLM auto-detection:
  - Groq API (free, cloud): used when GROQ_API_KEY is set in environment
  - Ollama (local):         used as fallback for local development
"""
import logging
from langchain_community.vectorstores import FAISS
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.prompts import PromptTemplate
from langchain_core.documents import Document

logger = logging.getLogger(__name__)

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
Paragraph 2 (Evidence): 2–3 specific achievements from the verified facts above that match the JD.
Paragraph 3 (Fit): Cultural/team fit + what the candidate will contribute.
Closing: Professional sign-off requesting an interview.

Write the full cover letter below (no metadata, no placeholders):
"""
)


def _build_llm():
    """
    Return the appropriate LLM client.
    Groq is preferred (free, fast, cloud-native). Falls back to Ollama for local dev.
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


def _build_embeddings():
    """
    Return embedding model.
    Groq does not provide embeddings — we use Ollama embeddings locally
    or HuggingFace sentence-transformers as a cloud fallback.
    """
    from app.core.config import settings  # noqa: PLC0415

    if settings.USE_GROQ:
        # Use a lightweight local embedding model that doesn't need Ollama
        from langchain_community.embeddings import HuggingFaceEmbeddings  # noqa: PLC0415
        logger.info("Embedding backend: HuggingFace (all-MiniLM-L6-v2)")
        return HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2")
    else:
        from langchain_community.embeddings import OllamaEmbeddings  # noqa: PLC0415
        logger.info("Embedding backend: Ollama (%s)", settings.OLLAMA_EMBED_MODEL)
        return OllamaEmbeddings(
            model=settings.OLLAMA_EMBED_MODEL,
            base_url=settings.OLLAMA_BASE_URL,
        )


def _extract_text(result) -> str:
    """Handle both AIMessage (Groq/ChatModels) and str (Ollama) responses."""
    return result.content if hasattr(result, "content") else str(result)


def generate_cover_letter(resume_text: str, job_description: str) -> dict:
    """
    Generate a zero-hallucination cover letter using RAG.
    Returns: dict with keys: 'cover_letter', 'rag_context', 'chunks_used'
    """
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=400,
        chunk_overlap=60,
        separators=["\n\n", "\n", ".", " ", ""],
    )
    chunks = splitter.split_text(resume_text)
    docs = [Document(page_content=chunk) for chunk in chunks]

    embeddings = _build_embeddings()
    vectorstore = FAISS.from_documents(docs, embeddings)

    retriever = vectorstore.as_retriever(search_kwargs={"k": 6})
    relevant_docs = retriever.invoke(job_description)
    rag_context = "\n\n---\n\n".join(doc.page_content for doc in relevant_docs)

    llm = _build_llm()
    chain = _COVER_LETTER_PROMPT | llm
    result = chain.invoke({
        "context": rag_context,
        "job_description": job_description,
    })
    cover_letter = _extract_text(result).strip()

    return {
        "cover_letter": cover_letter,
        "rag_context": rag_context,
        "chunks_used": len(relevant_docs),
    }


def generate_skill_gap_analysis(resume_text: str, job_description: str) -> dict:
    """
    Identify missing skills and generate prioritised learning recommendations.
    """
    from app.services.ats_scorer import calculate_ats_score, PRIORITY_KEYWORDS  # noqa: PLC0415

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
        chain = prompt | llm
        result = chain.invoke({"skills": ", ".join(priority_gaps)})
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
    """
    Generate 10 tailored interview questions based on the JD and candidate's resume.
    """
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
    chain = prompt | llm
    result = chain.invoke({
        "job_description": job_description[:1500],
        "resume_excerpt": resume_text[:1500],
    })
    output = _extract_text(result).strip()

    lines = [line.strip() for line in output.split("\n") if line.strip()]
    questions = [line for line in lines if line[0].isdigit() or line.startswith("-")]
    return questions[:10] if questions else [output]
