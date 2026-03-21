import json
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import get_current_user
from app.core.db import get_async_session
from app.models.resume import Resume, ResumeRead, ResumeReadWithText
from app.models.user import User
from app.services.file_extractor import extract_text_from_upload
from app.services.resume_parser import parse_resume

router = APIRouter()

MAX_RESUMES_PER_USER = 10


@router.post("/upload", response_model=ResumeRead, status_code=status.HTTP_201_CREATED)
async def upload_resume(
    name: Annotated[str, Form()],
    file: Annotated[UploadFile, File()],
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_async_session)],
):
    """Upload a resume (PDF, DOCX, or TXT). Extracts text and runs LLM-based structured parsing."""
    result = await session.execute(select(Resume).where(Resume.user_id == current_user.id))
    existing = result.scalars().all()
    if len(existing) >= MAX_RESUMES_PER_USER:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Maximum of {MAX_RESUMES_PER_USER} resumes per user. Delete one first.",
        )

    try:
        raw_text = await extract_text_from_upload(file)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))

    parsed = parse_resume(raw_text)
    parsed_json = parsed.model_dump_json()
    is_first = len(existing) == 0

    resume = Resume(
        user_id=current_user.id,
        name=name,
        original_filename=file.filename or "resume",
        raw_text=raw_text,
        parsed_json=parsed_json,
        is_active=is_first,
    )
    session.add(resume)
    await session.commit()
    await session.refresh(resume)
    return resume


@router.get("/", response_model=list[ResumeRead])
async def list_resumes(
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_async_session)],
):
    """List all resumes for the current user."""
    result = await session.execute(
        select(Resume).where(Resume.user_id == current_user.id).order_by(Resume.created_at.desc())
    )
    return result.scalars().all()


@router.get("/{resume_id}", response_model=ResumeReadWithText)
async def get_resume(
    resume_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_async_session)],
):
    """Get a specific resume including full raw text and parsed JSON."""
    resume = await session.get(Resume, resume_id)
    if not resume or resume.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resume not found.")
    return resume


@router.put("/{resume_id}/activate", response_model=ResumeRead)
async def activate_resume(
    resume_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_async_session)],
):
    """Set a resume as the active one (deactivates all others)."""
    result = await session.execute(select(Resume).where(Resume.user_id == current_user.id))
    all_resumes = result.scalars().all()

    target = next((r for r in all_resumes if r.id == resume_id), None)
    if not target:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resume not found.")

    for r in all_resumes:
        r.is_active = r.id == resume_id
        session.add(r)

    await session.commit()
    await session.refresh(target)
    return target


@router.delete("/{resume_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_resume(
    resume_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_async_session)],
):
    """Delete a resume."""
    resume = await session.get(Resume, resume_id)
    if not resume or resume.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resume not found.")
    await session.delete(resume)
    await session.commit()


@router.get("/{resume_id}/analysis")
async def get_resume_analysis(
    resume_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_async_session)],
):
    """Return the structured parsed analysis of a resume."""
    resume = await session.get(Resume, resume_id)
    if not resume or resume.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resume not found.")
    if not resume.parsed_json:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No analysis available.")
    return json.loads(resume.parsed_json)
