import logging
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import get_current_user
from app.core.db import get_async_session
from app.core.limiter import rate_limit
from app.models.resume import Resume
from app.models.user import User
from app.services.ats_scorer import calculate_ats_score
from app.services.cover_letter import generate_interview_questions, generate_skill_gap_analysis
from app.services.job_scraper import JobFetchError, fetch_job_description

router = APIRouter()
logger = logging.getLogger(__name__)


class AIRequest(BaseModel):
    job_description: str = Field(..., max_length=10_000)
    resume_id: uuid.UUID | None = None


class JobUrlRequest(BaseModel):
    url: str = Field(..., max_length=2000)


async def _get_resume_text(
    resume_id: uuid.UUID | None,
    current_user: User,
    session: AsyncSession,
) -> str:
    """Helper: resolve which resume to use and return its text."""
    if resume_id:
        resume = await session.get(Resume, resume_id)
        if not resume or resume.user_id != current_user.id:
            raise HTTPException(status_code=404, detail="Resume not found.")
    else:
        result = await session.execute(
            select(Resume).where(Resume.user_id == current_user.id, Resume.is_active.is_(True))
        )
        resume = result.scalars().first()
        if not resume:
            raise HTTPException(
                status_code=404,
                detail="No active resume. Upload a resume and activate it first.",
            )
    return resume.raw_text


@router.post("/ats-score")
@rate_limit("20/minute")
async def ats_score(
    request: Request,
    payload: AIRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_async_session)],
):
    """Score the resume against a job description. Rate limited: 20 req/min per IP."""
    resume_text = await _get_resume_text(payload.resume_id, current_user, session)
    result = calculate_ats_score(resume_text, payload.job_description)
    return {
        "score": result.score,
        "semantic_score": result.semantic_score,
        "keyword_score": result.keyword_score,
        "structure_score": result.structure_score,
        "matched_keywords": result.matched_keywords,
        "missing_keywords": result.missing_keywords,
        "recommendations": result.recommendations,
        "section_scores": result.section_scores,
        "breakdown": result.breakdown,
    }


@router.post("/skill-gap")
@rate_limit("20/minute")
async def skill_gap(
    request: Request,
    payload: AIRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_async_session)],
):
    """Perform a skill gap analysis. Rate limited: 20 req/min per IP."""
    resume_text = await _get_resume_text(payload.resume_id, current_user, session)
    try:
        result = generate_skill_gap_analysis(resume_text, payload.job_description)
    except Exception as exc:
        logger.error("Skill gap analysis failed: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="AI service temporarily unavailable. Please try again.",
        )
    return result


@router.post("/interview-questions")
@rate_limit("20/minute")
async def interview_questions(
    request: Request,
    payload: AIRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_async_session)],
):
    """Generate interview questions. Rate limited: 20 req/min per IP."""
    resume_text = await _get_resume_text(payload.resume_id, current_user, session)
    try:
        questions = generate_interview_questions(resume_text, payload.job_description)
    except Exception as exc:
        logger.error("Interview question generation failed: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="AI service temporarily unavailable. Please try again.",
        )
    return {"questions": questions, "count": len(questions)}


@router.post("/fetch-job")
@rate_limit("10/minute")
async def fetch_job_from_url(
    request: Request,
    payload: JobUrlRequest,
    current_user: Annotated[User, Depends(get_current_user)],
):
    """Fetch and extract a job description from any public URL (LinkedIn, Greenhouse, etc.).
    Rate limited: 10 req/min per IP to avoid hammering external sites.
    """
    try:
        result = await fetch_job_description(payload.url)
        return result
    except JobFetchError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
