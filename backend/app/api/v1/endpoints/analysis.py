import asyncio
import logging
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api.v1.deps import get_current_user
from app.core.db import get_async_session
from app.core.limiter import rate_limit
from app.core.utils import sanitize_text
from app.models.resume import Resume
from app.models.user import User
from app.services.ats_scorer import calculate_ats_score
from app.services.cover_letter import generate_interview_questions, generate_skill_gap_analysis

router = APIRouter()
logger = logging.getLogger(__name__)


class JobMatchRequest(BaseModel):
    resume_id: uuid.UUID
    job_description: str = Field(..., max_length=10_000)


@router.post("/job-match")
@rate_limit("20/minute")
async def job_match(
    request: Request,
    payload: JobMatchRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_async_session)],
):
    """Run ATS score, skill gap, and interview questions in parallel for one JD submission."""
    resume = await session.get(Resume, payload.resume_id)
    if not resume or resume.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resume not found.")

    jd = sanitize_text(payload.job_description)
    resume_text = resume.raw_text

    def _ats() -> dict:
        r = calculate_ats_score(resume_text, jd)
        return {
            "score": r.score,
            "semantic_score": r.semantic_score,
            "keyword_score": r.keyword_score,
            "structure_score": r.structure_score,
            "matched_keywords": r.matched_keywords,
            "missing_keywords": r.missing_keywords,
            "recommendations": r.recommendations,
            "section_scores": r.section_scores,
            "breakdown": r.breakdown,
        }

    def _skill_gap() -> dict:
        return generate_skill_gap_analysis(resume_text, jd)

    def _interview() -> list[str]:
        return generate_interview_questions(resume_text, jd)

    try:
        ats_result, skill_gap_result, interview_result = await asyncio.gather(
            asyncio.to_thread(_ats),
            asyncio.to_thread(_skill_gap),
            asyncio.to_thread(_interview),
        )
    except Exception as exc:
        logger.error("job-match fan-out failed: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="AI service temporarily unavailable. Please try again.",
        ) from exc

    return {
        "ats": ats_result,
        "skill_gap": skill_gap_result,
        "interview_questions": interview_result,
    }
