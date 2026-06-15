import asyncio
import logging
import uuid
from typing import Annotated

import redis
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api.v1.deps import get_current_user
from app.core.db import get_async_session
from app.core.limiter import rate_limit
from app.core.utils import _sanitize_jd_for_prompt, sanitize_text
from app.models.resume import Resume
from app.models.user import User
from app.services import task_state
from app.services.ats_scorer import calculate_ats_score
from app.services.cover_letter import generate_interview_questions, generate_skill_gap_analysis

router = APIRouter()
logger = logging.getLogger(__name__)

_SERVICE_ERROR = "AI service temporarily unavailable. Please try again."

# Step names surfaced live in the frontend while the analysis runs.
_STEPS = ("ats", "skill_gap", "interview")


class JobMatchRequest(BaseModel):
    resume_id: uuid.UUID
    job_description: str = Field(..., max_length=10_000)


def _ats_part(resume_text: str, jd: str) -> dict:
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


def _skill_gap_part(resume_text: str, jd: str) -> dict:
    return generate_skill_gap_analysis(resume_text, jd)


def _interview_part(resume_text: str, jd: str) -> list[str]:
    return generate_interview_questions(resume_text, jd)


async def _run_job_match_bg(task_id: str, resume_text: str, jd: str) -> None:
    """Run the three analyses, recording per-step progress for the live UI."""
    await task_state.set_status(task_id, "STARTED")

    async def tracked(step: str, fn):
        await task_state.set_step(task_id, step, "running")
        try:
            out = await asyncio.to_thread(fn, resume_text, jd)
        except Exception:
            await task_state.set_step(task_id, step, "failed")
            raise
        await task_state.set_step(task_id, step, "done")
        return out

    try:
        ats_result, skill_gap_result, interview_result = await asyncio.gather(
            tracked("ats", _ats_part),
            tracked("skill_gap", _skill_gap_part),
            tracked("interview", _interview_part),
        )
    except Exception as exc:
        logger.error("job-match task %s failed: %s", task_id, exc, exc_info=True)
        await task_state.set_status(task_id, "FAILURE", error=_SERVICE_ERROR)
        return

    await task_state.set_result(
        task_id,
        {
            "ats": ats_result,
            "skill_gap": skill_gap_result,
            "interview_questions": interview_result,
        },
    )


@router.post("/job-match")
@rate_limit("20/minute")
async def job_match(
    request: Request,
    payload: JobMatchRequest,
    background_tasks: BackgroundTasks,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_async_session)],
):
    """Queue ATS score, skill gap, and interview questions for one JD (202 + poll).

    Falls back to the old blocking single-response mode (200) if the Redis
    task store is unavailable — slower, but the feature stays up.
    """
    resume = await session.get(Resume, payload.resume_id)
    if not resume or resume.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resume not found.")

    jd = _sanitize_jd_for_prompt(sanitize_text(payload.job_description))
    resume_text = resume.raw_text

    task_id = await task_state.create("job_match", current_user.id, steps=list(_STEPS))
    if task_id:
        background_tasks.add_task(_run_job_match_bg, task_id, resume_text, jd)
        return JSONResponse(
            status_code=status.HTTP_202_ACCEPTED,
            content={"task_id": task_id, "status": "PENDING"},
        )

    logger.warning("job-match running inline — Redis task store unavailable")
    try:
        ats_result, skill_gap_result, interview_result = await asyncio.gather(
            asyncio.to_thread(_ats_part, resume_text, jd),
            asyncio.to_thread(_skill_gap_part, resume_text, jd),
            asyncio.to_thread(_interview_part, resume_text, jd),
        )
    except Exception as exc:
        logger.error("job-match fan-out failed: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=_SERVICE_ERROR,
        ) from exc

    return {
        "ats": ats_result,
        "skill_gap": skill_gap_result,
        "interview_questions": interview_result,
    }


@router.get("/task/{task_id}")
async def poll_analysis_task(
    task_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
):
    """Poll an async analysis task — same status contract as the cover-letter poll."""
    try:
        task = await task_state.get(task_id)
    except redis.RedisError as exc:
        logger.warning("task store unreachable while polling %s: %s", task_id, exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Task status is temporarily unavailable. Retry shortly.",
        ) from exc

    # A foreign task reads as missing — don't reveal that the id exists.
    if not task or task.get("user_id") != str(current_user.id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Unknown or expired task.",
        )

    return {
        "task_id": task_id,
        "status": task["status"],
        "steps": task["steps"],
        "result": task["result"] if task["status"] == "SUCCESS" else None,
        "error": task.get("error"),
    }
