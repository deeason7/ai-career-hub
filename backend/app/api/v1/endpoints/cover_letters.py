"""Cover letter generation, status polling, and PDF download endpoints."""

import io
import logging
import uuid
from typing import Annotated

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from sqlmodel import Session, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api.v1.deps import get_current_user
from app.core.config import settings
from app.core.db import get_async_session, sync_engine
from app.core.limiter import rate_limit
from app.core.utils import sanitize_text
from app.models.cover_letter import CoverLetter, CoverLetterCreate, CoverLetterRead
from app.models.cover_letter_revision import (
    CoverLetterRevision,
    CoverLetterRevisionCreate,
    CoverLetterRevisionRead,
)
from app.models.resume import Resume
from app.models.user import User
from app.services.cover_letter import generate_cover_letter, refine_cover_letter
from app.services.pdf_generator import generate_cover_letter_pdf
from app.services.qa_service import HALLUCINATION_THRESHOLD

logger = logging.getLogger(__name__)


router = APIRouter()

# DB status values mapped to task-status names the frontend already understands.
_STATUS_MAP = {
    "processing": "STARTED",
    "pending": "PENDING",
    "success": "SUCCESS",
    "failure": "FAILURE",
}


async def _dispatch_to_n8n(cover_letter_id: str, resume_text: str, job_description: str) -> bool:
    """POST to n8n Cloud webhook to trigger the cover letter workflow.

    Returns True if n8n accepted the request, False if unreachable
    (caller will fall back to local BackgroundTasks).
    """
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                settings.N8N_WEBHOOK_URL,
                json={
                    "cover_letter_id": cover_letter_id,
                    "resume_text": resume_text[:8000],  # Limit payload size
                    "job_description": job_description[:4000],
                    "callback_url": f"{settings.BASE_URL}{settings.API_V1_STR}/webhooks/n8n/cover-letters/{cover_letter_id}/callback",
                },
                headers={"X-Webhook-Secret": settings.N8N_WEBHOOK_SECRET},
            )
            if response.status_code < 300:
                logger.info("Dispatched to n8n: %s", cover_letter_id)
                return True
            logger.warning(
                "n8n returned %d for %s — falling back to local",
                response.status_code,
                cover_letter_id,
            )
    except (httpx.RequestError, httpx.TimeoutException) as exc:
        logger.warning(
            "n8n unreachable for %s (%s) — falling back to local",
            cover_letter_id,
            type(exc).__name__,
        )
    return False


def _run_cover_letter_bg(cover_letter_id: str, resume_text: str, job_description: str) -> None:
    """Generate a cover letter, run QA review, and persist the result."""
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
            result = generate_cover_letter(resume_text, job_description)
            cover_letter_text = result["cover_letter"]

            try:
                verdict = review_cover_letter(
                    cover_letter=cover_letter_text,
                    resume_text=resume_text,
                    job_description=job_description,
                )
            except Exception as qa_exc:
                logger.warning(
                    "QA review failed for %s (attempt %d): %s",
                    cover_letter_id,
                    attempt + 1,
                    qa_exc,
                )
                verdict = None
                break

            if passes_qa(verdict):
                logger.info(
                    "QA passed for %s on attempt %d (honesty=%d)",
                    cover_letter_id,
                    attempt + 1,
                    verdict.honesty_score,
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

        # Persist result
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
    """Dispatch cover letter generation (async, returns 202).

    Uses n8n webhook when configured, falls back to in-process BackgroundTasks.
    """
    if payload.resume_id:
        resume = await session.get(Resume, payload.resume_id)
        if not resume or resume.user_id != current_user.id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resume not found.")
    else:
        result = await session.exec(
            select(Resume).where(Resume.user_id == current_user.id, Resume.is_active.is_(True))
        )
        resume = result.first()
        if not resume:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No active resume found. Please upload and activate a resume first.",
            )

    task_id = str(uuid.uuid4())
    cover_letter = CoverLetter(
        user_id=current_user.id,
        resume_id=resume.id,
        job_description=sanitize_text(payload.job_description),
        task_id=task_id,
        status="processing",
    )
    session.add(cover_letter)
    await session.commit()
    await session.refresh(cover_letter)

    dispatched = False
    if settings.N8N_ENABLED:
        dispatched = await _dispatch_to_n8n(
            cover_letter_id=str(cover_letter.id),
            resume_text=resume.raw_text,
            job_description=payload.job_description,
        )

    if not dispatched:
        background_tasks.add_task(
            _run_cover_letter_bg,
            str(cover_letter.id),
            resume.raw_text,
            sanitize_text(payload.job_description),
        )

    return cover_letter


@router.get("/", response_model=list[CoverLetterRead])
async def list_cover_letters(
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_async_session)],
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
):
    """Return generated cover letters for the current user. Paginated (default 20)."""
    result = await session.exec(
        select(CoverLetter)
        .where(CoverLetter.user_id == current_user.id)
        .order_by(CoverLetter.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    return result.all()


@router.get("/task/{task_id}")
async def poll_task_status(
    task_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_async_session)],
):
    """Poll cover letter generation status by task_id — reads from DB, no Celery."""
    result = await session.exec(
        select(CoverLetter).where(
            CoverLetter.task_id == task_id,
            CoverLetter.user_id == current_user.id,
        )
    )
    cl = result.first()
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
            "passed": cl.qa_score_honesty >= HALLUCINATION_THRESHOLD,
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


def _run_refine_bg(
    revision_id: str,
    cover_letter_id: str,
    original_text: str,
    resume_text: str,
    job_description: str,
    user_command: str,
) -> None:
    from app.services.qa_service import review_cover_letter  # noqa: PLC0415

    logger.info("Background: refining cover letter %s (revision %s)", cover_letter_id, revision_id)
    try:
        result = refine_cover_letter(original_text, resume_text, job_description, user_command)
        refined_text = result["cover_letter"]

        try:
            verdict = review_cover_letter(
                cover_letter=refined_text,
                resume_text=resume_text,
                job_description=job_description,
            )
        except Exception as exc:
            logger.warning("QA review failed for revision %s: %s", revision_id, exc)
            verdict = None

        with Session(sync_engine) as session:
            rev = session.get(CoverLetterRevision, uuid.UUID(revision_id))
            if rev:
                rev.generated_text = refined_text
                if verdict:
                    rev.qa_score_honesty = verdict.honesty_score
                    rev.qa_score_tone = verdict.tone_score
                    rev.set_qa_flags(verdict.flags)
                session.add(rev)
                session.commit()
    except Exception as exc:
        logger.error(
            "Refine background task failed for revision %s: %s", revision_id, exc, exc_info=True
        )


@router.post(
    "/{cover_letter_id}/refine",
    response_model=CoverLetterRevisionRead,
    status_code=status.HTTP_202_ACCEPTED,
)
@rate_limit("5/minute")
async def refine_cover_letter_endpoint(
    request: Request,
    cover_letter_id: uuid.UUID,
    payload: CoverLetterRevisionCreate,
    background_tasks: BackgroundTasks,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_async_session)],
):
    """Queue a targeted refinement of an existing cover letter. Returns the new revision (202)."""
    cl = await session.get(CoverLetter, cover_letter_id)
    if not cl or cl.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cover letter not found.")
    if not cl.generated_text:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cover letter has not been generated yet.",
        )

    resume = await session.get(Resume, cl.resume_id)
    if not resume:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resume not found.")

    # Determine next version number
    from sqlalchemy import func  # noqa: PLC0415

    conn = await session.connection()
    count_result = await conn.execute(
        select(func.count()).where(CoverLetterRevision.cover_letter_id == cover_letter_id)
    )
    next_version = (count_result.scalar_one() or 0) + 1

    revision = CoverLetterRevision(
        cover_letter_id=cover_letter_id,
        version_number=next_version,
        generated_text=cl.generated_text,  # placeholder until bg task completes
        user_command=sanitize_text(payload.command),
    )
    session.add(revision)
    await session.commit()
    await session.refresh(revision)

    background_tasks.add_task(
        _run_refine_bg,
        str(revision.id),
        str(cover_letter_id),
        cl.generated_text,
        resume.raw_text,
        cl.job_description,
        sanitize_text(payload.command),
    )
    return revision


@router.get("/{cover_letter_id}/revisions", response_model=list[CoverLetterRevisionRead])
async def list_revisions(
    cover_letter_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_async_session)],
):
    """List all refinement revisions for a cover letter, newest first."""
    cl = await session.get(CoverLetter, cover_letter_id)
    if not cl or cl.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cover letter not found.")

    result = await session.exec(
        select(CoverLetterRevision)
        .where(CoverLetterRevision.cover_letter_id == cover_letter_id)
        .order_by(CoverLetterRevision.version_number.desc())
    )
    return result.all()


@router.post(
    "/{cover_letter_id}/revisions/{version_number}/activate",
    response_model=CoverLetterRead,
)
async def activate_revision(
    cover_letter_id: uuid.UUID,
    version_number: int,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_async_session)],
):
    """Promote a revision to the canonical cover letter text."""
    cl = await session.get(CoverLetter, cover_letter_id)
    if not cl or cl.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cover letter not found.")

    result = await session.exec(
        select(CoverLetterRevision).where(
            CoverLetterRevision.cover_letter_id == cover_letter_id,
            CoverLetterRevision.version_number == version_number,
        )
    )
    revision = result.first()
    if not revision:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Revision not found.")

    cl.generated_text = revision.generated_text
    if revision.qa_score_honesty is not None:
        cl.qa_score_honesty = revision.qa_score_honesty
        cl.qa_score_tone = revision.qa_score_tone
        cl.set_qa_flags(revision.get_qa_flags())
    session.add(cl)
    await session.commit()
    await session.refresh(cl)
    return cl
