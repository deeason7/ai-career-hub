import uuid
from typing import Annotated, Optional
from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlmodel import select
from app.core.db import get_async_session
from app.api.v1.deps import get_current_user
from app.models.user import User
from app.models.resume import Resume
from app.models.cover_letter import CoverLetter, CoverLetterCreate, CoverLetterRead
from app.tasks.ai_tasks import generate_cover_letter_task

router = APIRouter()


@router.post("/generate", response_model=CoverLetterRead, status_code=status.HTTP_202_ACCEPTED)
async def generate_cover_letter(
    payload: CoverLetterCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_async_session)],
):
    """
    Dispatch an async Celery job to generate a cover letter.
    - If resume_id is provided, use that resume.
    - Otherwise, use the user's active resume.
    Returns the CoverLetter record with task_id for polling.
    """
    # Resolve which resume to use
    if payload.resume_id:
        resume = await session.get(Resume, payload.resume_id)
        if not resume or resume.user_id != current_user.id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resume not found.")
    else:
        result = await session.exec(
            select(Resume).where(Resume.user_id == current_user.id, Resume.is_active == True)
        )
        resume = result.first()
        if not resume:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No active resume found. Please upload a resume and activate it first.",
            )

    # Create a pending CoverLetter record
    cover_letter = CoverLetter(
        user_id=current_user.id,
        resume_id=resume.id,
        job_description=payload.job_description,
        status="pending",
    )
    session.add(cover_letter)
    await session.commit()
    await session.refresh(cover_letter)

    # Dispatch async Celery task
    task = generate_cover_letter_task.delay(
        str(cover_letter.id),
        resume.raw_text,
        payload.job_description,
    )

    # Save task_id to the record
    cover_letter.task_id = task.id
    cover_letter.status = "processing"
    session.add(cover_letter)
    await session.commit()
    await session.refresh(cover_letter)

    return cover_letter


@router.get("/", response_model=list[CoverLetterRead])
async def list_cover_letters(
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_async_session)],
):
    """Return all generated cover letters for the current user."""
    result = await session.exec(
        select(CoverLetter)
        .where(CoverLetter.user_id == current_user.id)
        .order_by(CoverLetter.created_at.desc())
    )
    return result.all()


@router.get("/task/{task_id}")
async def poll_task_status(
    task_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
):
    """
    Poll a Celery task by ID.
    Returns: {status, result, cover_letter_id}
    """
    from app.tasks.celery_app import celery_app
    from celery.result import AsyncResult

    task_result = AsyncResult(task_id, app=celery_app)
    return {
        "task_id": task_id,
        "status": task_result.status,
        "result": task_result.result if task_result.ready() else None,
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
