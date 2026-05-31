"""Agent workflow endpoints — orchestrate multi-step job analysis."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from app.api.v1.deps import get_current_user
from app.core.db import engine
from app.models.resume import Resume
from app.models.user import User

router = APIRouter()


class AgentRequest(BaseModel):
    job_url: str = Field(..., min_length=10)
    resume_id: uuid.UUID


class AgentResponse(BaseModel):
    status: str
    steps: list[dict]
    summary: dict
    full_results: dict
    errors: list[str]
    total_duration_ms: int


def _get_resume_text(resume_id: uuid.UUID, user_id: uuid.UUID) -> str:
    """Fetch resume text from DB, verifying ownership."""
    with Session(engine) as session:
        resume = session.exec(
            select(Resume).where(Resume.id == resume_id, Resume.user_id == user_id)
        ).first()
        if not resume:
            raise HTTPException(status_code=404, detail="Resume not found")
        if not resume.extracted_text:
            raise HTTPException(status_code=400, detail="Resume has no extracted text")
        return resume.extracted_text


@router.post("/analyze", response_model=AgentResponse)
def run_agent_analysis(
    request: AgentRequest,
    current_user: Annotated[User, Depends(get_current_user)],
):
    """Run the full agentic workflow: scrape → extract → research → score → generate."""
    from app.services.agent_graph import run_agent

    resume_text = _get_resume_text(request.resume_id, current_user.id)

    result = run_agent(
        job_url=str(request.job_url),
        resume_text=resume_text,
        user_id=str(current_user.id),
    )
    return AgentResponse(**result)
