import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import get_current_user
from app.core.db import get_async_session
from app.models.job_application import (
    JobApplication,
    JobApplicationCreate,
    JobApplicationRead,
    JobApplicationUpdate,
)
from app.models.user import User

router = APIRouter()

VALID_STATUSES = {
    "wishlist",
    "applied",
    "phone_screen",
    "interview",
    "offer",
    "rejected",
    "accepted",
}


@router.post("/", response_model=JobApplicationRead, status_code=status.HTTP_201_CREATED)
async def create_application(
    payload: JobApplicationCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_async_session)],
):
    """Create a new job application entry."""
    if payload.status not in VALID_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid status. Must be one of: {', '.join(VALID_STATUSES)}",
        )
    job_app = JobApplication(user_id=current_user.id, **payload.model_dump())
    session.add(job_app)
    await session.commit()
    await session.refresh(job_app)
    return job_app


@router.get("/", response_model=list[JobApplicationRead])
async def list_applications(
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_async_session)],
    status_filter: str | None = None,
):
    """List all job applications. Optionally filter by status."""
    query = select(JobApplication).where(JobApplication.user_id == current_user.id)
    if status_filter:
        query = query.where(JobApplication.status == status_filter)
    query = query.order_by(JobApplication.created_at.desc())
    result = await session.execute(query)
    return result.scalars().all()


@router.get("/stats")
async def application_stats(
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_async_session)],
):
    """Return a breakdown of job applications by status."""
    total_result = await session.execute(
        select(func.count()).where(JobApplication.user_id == current_user.id)
    )
    total = total_result.scalar_one()

    breakdown_result = await session.execute(
        select(JobApplication.status, func.count())
        .where(JobApplication.user_id == current_user.id)
        .group_by(JobApplication.status)
    )
    breakdown = {s: 0 for s in VALID_STATUSES}
    for row_status, count in breakdown_result.all():
        breakdown[row_status] = count

    return {"total": total, "by_status": breakdown}


@router.patch("/{app_id}", response_model=JobApplicationRead)
async def update_application(
    app_id: uuid.UUID,
    payload: JobApplicationUpdate,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_async_session)],
):
    """Update any field on a job application (partial update)."""
    job_app = await session.get(JobApplication, app_id)
    if not job_app or job_app.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Application not found.")
    if payload.status and payload.status not in VALID_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid status. Must be one of: {', '.join(VALID_STATUSES)}",
        )
    update_data = payload.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(job_app, key, value)
    job_app.updated_at = datetime.now(UTC)
    session.add(job_app)
    await session.commit()
    await session.refresh(job_app)
    return job_app


@router.delete("/{app_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_application(
    app_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_async_session)],
):
    """Delete a job application."""
    job_app = await session.get(JobApplication, app_id)
    if not job_app or job_app.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Application not found.")
    await session.delete(job_app)
    await session.commit()
