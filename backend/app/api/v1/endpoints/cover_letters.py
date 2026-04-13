"""Cover letter generation, status polling, and PDF download endpoints."""
import io
import logging
import uuid
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import Session

from app.api.v1.deps import get_current_user
from app.core.db import get_async_session, sync_engine
from app.core.limiter import rate_limit
from app.models.cover_letter import CoverLetter, CoverLetterCreate, CoverLetterRead
from app.models.resume import Resume
from app.models.user import User
from app.services.cover_letter import generate_cover_letter
from app.services.pdf_generator import generate_cover_letter_pdf

logger = logging.getLogger(__name__)

router = APIRouter()

# DB status values mapped to task-status names the frontend already understands.
_STATUS_MAP = {
    "processing": "STARTED",
    "pending": "PENDING",
    "success": "SUCCESS",
    "failure": "FAILURE",
}


def _run_cover_letter_bg(cover_letter_id: str, resume_text: str, job_description: str) -> None:
    """Background thread: generates cover letter, runs QA review, persists result.

    Pipeline:
      1. Generate cover letter via instructor (Groq) or LangChain (Ollama)
      2. Run AI-as-a-Judge QA review → get honesty/tone scores
      3. If honesty < threshold, auto-regenerate (up to MAX_QA_RETRIES times)
      4. Persist the best result with QA scores to DB
      5. If still below threshold after retries, save anyway but status reflects it
    """
    from app.services.qa_service import (  # noqa: PLC0415
        HALLUCINATION_THRESHOLD,
        MAX_QA_RETRIES,
        passes_qa,
        review_cover_letter,
    )

    logger.info("Background: generating cover letter %s", cover_letter_id)
    try:
        cover_letter_text = None
        verdict = None
        retries = 0

        for attempt in range(1 + MAX_QA_RETRIES):
            # Step 1: Generate
            result = generate_cover_letter(resume_text, job_description)
            cover_letter_text = result["cover_letter"]

            # Step 2: QA Review
            try:
                verdict = review_cover_letter(
                    cover_letter=cover_letter_text,
                    resume_text=resume_text,
                    job_description=job_description,
                )
            except Exception as qa_exc:
                # QA review failed (LLM error, validation error, etc.)
                # Save the letter without QA scores rather than losing it.
                logger.warning(
                    "QA review failed for %s (attempt %d): %s",
                    cover_letter_id, attempt + 1, qa_exc,
                )
                verdict = None
                break

            # Step 3: Check threshold
            if passes_qa(verdict):
                logger.info(
                    "QA passed for %s on attempt %d (honesty=%d)",
                    cover_letter_id, attempt + 1, verdict.honesty_score,
                )
                break

            retries = attempt + 1
            if retries <= MAX_QA_RETRIES:
                logger.info(
                    "QA below threshold for %s (honesty=%d < %d), regenerating (attempt %d/%d)",
                    cover_letter_id,
                    verdict.honesty_score,
                    HALLUCINATION_THRESHOLD,
                    retries,
                    MAX_QA_RETRIES,
                )

        # Step 4: Persist result with QA scores
        with Session(sync_engine) as session:
            cl = session.get(CoverLetter, uuid.UUID(cover_letter_id))
            if cl:
                cl.generated_text = cover_letter_text
                cl.status = "success"
                cl.qa_retries = retries

                if verdict:
                    cl.qa_score_honesty = verdict.honesty_score
                    cl.qa_score_tone = verdict.tone_score
                    cl.set_qa_flags(verdict.flags)

                session.add(cl)
                session.commit()
                logger.info(
                    "Cover letter saved: %s (honesty=%s, retries=%d)",
                    cover_letter_id,
                    verdict.honesty_score if verdict else "N/A",
                    retries,
                )

    except Exception as exc:
        logger.error("Cover letter background task failed: %s", exc, exc_info=True)
        try:
            with Session(sync_engine) as session:
                cl = session.get(CoverLetter, uuid.UUID(cover_letter_id))
                if cl:
                    cl.status = "failure"
                    session.add(cl)
                    session.commit()
        except Exception as inner_exc:
            logger.error("Failed to persist failure status for %s: %s", cover_letter_id, inner_exc)


@router.post("/generate", response_model=CoverLetterRead, status_code=status.HTTP_202_ACCEPTED)
@rate_limit("5/minute")
async def generate_cover_letter_endpoint(
    request: Request,
    payload: CoverLetterCreate,
    background_tasks: BackgroundTasks,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_async_session)],
):
    """Dispatch a background task to generate a cover letter. Rate limited: 5 req/min per IP."""
    if payload.resume_id:
        resume = await session.get(Resume, payload.resume_id)
        if not resume or resume.user_id != current_user.id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resume not found.")
    else:
        result = await session.execute(
            select(Resume).where(
                Resume.user_id == current_user.id, Resume.is_active.is_(True)
            )
        )
        resume = result.scalars().first()
        if not resume:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No active resume found. Please upload and activate a resume first.",
            )

    task_id = str(uuid.uuid4())
    cover_letter = CoverLetter(
        user_id=current_user.id,
        resume_id=resume.id,
        job_description=payload.job_description,
        task_id=task_id,
        status="processing",
    )
    session.add(cover_letter)
    await session.commit()
    await session.refresh(cover_letter)

    background_tasks.add_task(
        _run_cover_letter_bg,
        str(cover_letter.id),
        resume.raw_text,
        payload.job_description,
    )
    return cover_letter


@router.get("/", response_model=list[CoverLetterRead])
async def list_cover_letters(
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_async_session)],
):
    """Return all generated cover letters for the current user."""
    result = await session.execute(
        select(CoverLetter)
        .where(CoverLetter.user_id == current_user.id)
        .order_by(CoverLetter.created_at.desc())
    )
    return result.scalars().all()


@router.get("/task/{task_id}")
async def poll_task_status(
    task_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_async_session)],
):
    """Poll cover letter generation status by task_id — reads from DB, no Celery."""
    result = await session.execute(
        select(CoverLetter).where(
            CoverLetter.task_id == task_id,
            CoverLetter.user_id == current_user.id,
        )
    )
    cl = result.scalars().first()
    if not cl:
        return {"task_id": task_id, "status": "PENDING", "result": None}

    response = {
        "task_id": task_id,
        "status": _STATUS_MAP.get(cl.status, "PENDING"),
        "result": cl.generated_text if cl.status == "success" else None,
    }

    # Include QA data when available — frontend can display scores and warnings
    if cl.status == "success" and cl.qa_score_honesty is not None:
        response["qa"] = {
            "honesty_score": cl.qa_score_honesty,
            "tone_score": cl.qa_score_tone,
            "flags": cl.get_qa_flags(),
            "retries": cl.qa_retries,
            "passed": cl.qa_score_honesty >= 6,
        }

    return response


@router.get("/{cover_letter_id}", response_model=CoverLetterRead)
async def get_cover_letter(
    cover_letter_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_async_session)],
):
    """Return a specific cover letter record."""
    cl = await session.get(CoverLetter, cover_letter_id)
    if not cl or cl.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cover letter not found.")
    return cl


@router.get("/{cover_letter_id}/pdf")
async def download_cover_letter_pdf(
    cover_letter_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> StreamingResponse:
    """Stream a professionally formatted PDF of the cover letter."""
    cl = await session.get(CoverLetter, cover_letter_id)
    if not cl or cl.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cover letter not found.")
    if not cl.generated_text:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cover letter has not been generated yet.",
        )

    user_name = current_user.full_name or ""
    pdf_bytes = generate_cover_letter_pdf(cl.generated_text, user_name=user_name)

    filename = f"cover_letter_{str(cover_letter_id)[:8]}.pdf"
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
