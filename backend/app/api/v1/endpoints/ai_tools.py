import uuid
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlmodel import select
from app.core.db import get_async_session
from app.api.v1.deps import get_current_user
from app.models.user import User
from app.models.resume import Resume
from app.services.ats_scorer import calculate_ats_score
from app.services.cover_letter import generate_skill_gap_analysis, generate_interview_questions

router = APIRouter()


class AIRequest(BaseModel):
    job_description: str
    resume_id: uuid.UUID | None = None  # If None, uses active resume


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
        result = await session.exec(
            select(Resume).where(Resume.user_id == current_user.id, Resume.is_active == True)
        )
        resume = result.first()
        if not resume:
            raise HTTPException(
                status_code=404,
                detail="No active resume. Upload a resume and activate it first.",
            )
    return resume.raw_text


@router.post("/ats-score")
async def ats_score(
    payload: AIRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_async_session)],
):
    """
    Score the resume against a job description using the ATS scorer.
    Returns overall score, breakdown, matched/missing keywords, and recommendations.
    """
    resume_text = await _get_resume_text(payload.resume_id, current_user, session)
    result = calculate_ats_score(resume_text, payload.job_description)
    return {
        "score": result.score,
        "keyword_score": result.keyword_score,
        "structure_score": result.structure_score,
        "matched_keywords": result.matched_keywords,
        "missing_keywords": result.missing_keywords,
        "recommendations": result.recommendations,
        "breakdown": result.breakdown,
    }


@router.post("/skill-gap")
async def skill_gap(
    payload: AIRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_async_session)],
):
    """
    Perform a skill gap analysis between the resume and job description.
    Returns matched skills, missing skills, priority gaps, and learning recommendations.
    """
    resume_text = await _get_resume_text(payload.resume_id, current_user, session)
    result = generate_skill_gap_analysis(resume_text, payload.job_description)
    return result


@router.post("/interview-questions")
async def interview_questions(
    payload: AIRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_async_session)],
):
    """
    Generate 10 tailored interview questions based on the resume and job description.
    """
    resume_text = await _get_resume_text(payload.resume_id, current_user, session)
    questions = generate_interview_questions(resume_text, payload.job_description)
    return {"questions": questions, "count": len(questions)}
