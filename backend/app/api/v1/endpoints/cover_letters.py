"""Cover letter endpoints — uses FastAPI BackgroundTasks instead of Celery.

No separate worker service needed: generation runs as a thread inside the API process.
"""
import logging
import uuid
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import Session

from app.api.v1.deps import get_current_user
from app.core.db import get_async_session, sync_engine
from app.core.limiter import limiter
from app.models.cover_letter import CoverLetter, CoverLetterCreate, CoverLetterRead
from app.models.resume import Resume
from app.models.user import User
from app.services.cover_letter import generate_cover_letter

logger = logging.getLogger(__name__)

router = APIRouter()

# Map DB status → Celery-compatible names (frontend polls these)
_STATUS_MAP = {
    "processing": "STARTED",
    "pending": "PENDING",
    "success": "SUCCESS",
    "failure": "FAILURE",
}


def _run_cover_letter_bg(cover_letter_id: str, resume_text: str, job_description: str) -> None:
    """Background thread: generates cover letter and persists result to DB."""
    logger.info(f"Background: generating cover letter {cover_letter_id}")
    try:
        result = generate_cover_letter(resume_text, job_description)
        cover_letter_text = result["cover_letter"]

        with Session(sync_engine) as session:
            cl = session.get(CoverLetter, uuid.UUID(cover_letter_id))
            if cl:
                cl.generated_text = cover_letter_text
                cl.status = "success"
                session.add(cl)
                session.commit()
                logger.info(f"Cover letter saved: {cover_letter_id}")

    except Exception as exc:
        logger.error(f"Cover letter background task failed: {exc}", exc_info=True)
        try:
            with Session(sync_engine) as session:
                cl = session.get(CoverLetter, uuid.UUID(cover_letter_id))
                if cl:
                    cl.status = "failure"
                    session.add(cl)
                    session.commit()
        except Exception:
            pass


@router.post("/generate", response_model=CoverLetterRead, status_code=status.HTTP_202_ACCEPTED)
@limiter.limit("5/minute")
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

    return {
        "task_id": task_id,
        "status": _STATUS_MAP.get(cl.status, "PENDING"),
        "result": cl.generated_text if cl.status == "success" else None,
    }


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
