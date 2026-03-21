"""
Cover Letter Generator Service

Uses a RAG pipeline with FAISS + Ollama to generate honest, resume-grounded cover letters.
Zero-hallucination: only uses facts retrieved from the candidate's resume.
"""
import logging
from langchain_community.llms import Ollama
from langchain_community.embeddings import OllamaEmbeddings
from langchain_community.vectorstores import FAISS
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.prompts import PromptTemplate
from langchain_core.documents import Document
from app.core.config import settings

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


def _ensure_models_available(ollama_url: str):
    """Pull Ollama models if not already available."""
    import requests
    for model in [settings.OLLAMA_EMBED_MODEL, settings.OLLAMA_LLM_MODEL]:
        try:
            resp = requests.get(f"{ollama_url}/api/tags", timeout=5)
            if resp.status_code == 200:
                available = [m["name"] for m in resp.json().get("models", [])]
                if model not in available and f"{model}:latest" not in available:
                    logger.info(f"Pulling model: {model}")
                    requests.post(f"{ollama_url}/api/pull", json={"name": model}, timeout=300)
        except Exception as e:
            logger.warning(f"Could not verify/pull model {model}: {e}")


def generate_cover_letter(resume_text: str, job_description: str) -> dict:
    """
    Generate a zero-hallucination cover letter using RAG.

    Returns:
        dict with keys: 'cover_letter', 'rag_context', 'chunks_used'
    """
    ollama_url = settings.OLLAMA_BASE_URL
    _ensure_models_available(ollama_url)

    # --- Step 1: Chunk the resume ---
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=400,
        chunk_overlap=60,
        separators=["\n\n", "\n", ".", " ", ""],
    )
    chunks = splitter.split_text(resume_text)
    docs = [Document(page_content=chunk) for chunk in chunks]

    # --- Step 2: Embed into FAISS ---
    embeddings = OllamaEmbeddings(
        model=settings.OLLAMA_EMBED_MODEL,
        base_url=ollama_url,
    )
    vectorstore = FAISS.from_documents(docs, embeddings)

    # --- Step 3: Retrieve top-k resume facts matching the JD ---
    retriever = vectorstore.as_retriever(search_kwargs={"k": 6})
    relevant_docs = retriever.invoke(job_description)
    rag_context = "\n\n---\n\n".join(doc.page_content for doc in relevant_docs)

    # --- Step 4: Generate cover letter ---
    llm = Ollama(
        model=settings.OLLAMA_LLM_MODEL,
        base_url=ollama_url,
    )
    chain = _COVER_LETTER_PROMPT | llm
    cover_letter = chain.invoke({
        "context": rag_context,
        "job_description": job_description,
    })

    return {
        "cover_letter": cover_letter.strip(),
        "rag_context": rag_context,
        "chunks_used": len(relevant_docs),
    }


def generate_skill_gap_analysis(resume_text: str, job_description: str) -> dict:
    """
    Identify missing skills from the job description not present in the resume.
    Returns structured skill gap with learning recommendations.
    """
    from app.services.ats_scorer import calculate_ats_score, _tokenize, PRIORITY_KEYWORDS
    import re

    ats = calculate_ats_score(resume_text, job_description)
    missing = ats.missing_keywords[:15]

    # Use LLM for learning recommendations on priority gaps
    priority_gaps = [kw for kw in missing if kw in PRIORITY_KEYWORDS][:5]

    recommendations = []
    if priority_gaps:
        llm = Ollama(model=settings.OLLAMA_LLM_MODEL, base_url=settings.OLLAMA_BASE_URL)
        prompt = PromptTemplate.from_template(
            "For a job seeker missing these skills: {skills}\n"
            "Give 3 specific, actionable learning recommendations (course name, platform, timeline).\n"
            "Be concise. Format as a numbered list."
        )
        chain = prompt | llm
        recs_text = chain.invoke({"skills": ", ".join(priority_gaps)})
        recommendations = [r.strip() for r in recs_text.strip().split("\n") if r.strip()]

    return {
        "ats_score": ats.score,
        "matched_skills": ats.matched_keywords[:20],
        "missing_skills": missing,
        "priority_gaps": priority_gaps,
        "learning_recommendations": recommendations,
    }


def generate_interview_questions(resume_text: str, job_description: str) -> list[str]:
    """
    Generate 10 tailored interview questions based on the JD and the candidate's resume.
    """
    llm = Ollama(model=settings.OLLAMA_LLM_MODEL, base_url=settings.OLLAMA_BASE_URL)
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
    output = chain.invoke({
        "job_description": job_description[:1500],
        "resume_excerpt": resume_text[:1500],
    })

    lines = [l.strip() for l in output.strip().split("\n") if l.strip()]
    questions = [l for l in lines if l[0].isdigit() or l.startswith("-")]
    return questions[:10] if questions else [output.strip()]
