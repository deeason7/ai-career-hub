"""Agent workflow endpoints — orchestrate multi-step job analysis."""

import asyncio
import logging
import uuid
from typing import Annotated

import redis
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api.v1.deps import get_current_user
from app.core.db import get_async_session
from app.core.limiter import rate_limit
from app.models.resume import Resume
from app.models.user import User
from app.services import task_state

router = APIRouter()
logger = logging.getLogger(__name__)

# The seven pipeline nodes in execution order — pre-registered so the frontend
# can show the full checklist before the first step lands.
_AGENT_STEPS = (
    "scrape_job",
    "extract_metadata",
    "search_company",
    "score_ats",
    "analyze_gaps",
    "write_cover_letter",
    "generate_questions",
)


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


def _run_agent_bg(task_id: str, job_url: str, resume_text: str, user_id: str) -> None:
    """Run the pipeline in the threadpool, mirroring each step into the task store.

    Must stay a sync function: the scrape tool drives its async fetch with
    asyncio.run(), which only works in a thread that has no running event loop.
    """
    from app.services.agent_graph import run_agent  # noqa: PLC0415

    task_state.set_status_sync(task_id, "STARTED")

    def on_step(state: dict) -> None:
        for record in state.get("steps_completed", []):
            task_state.set_step_sync(task_id, record["name"], record["status"])

    try:
        result = run_agent(
            job_url=job_url, resume_text=resume_text, user_id=user_id, on_step=on_step
        )
    except Exception as exc:
        logger.error("agent task %s failed: %s", task_id, exc, exc_info=True)
        task_state.set_status_sync(
            task_id, "FAILURE", error="The agent run failed. Please try again."
        )
        return

    task_state.set_result_sync(task_id, result)


@router.post("/analyze")
@rate_limit("5/minute")
async def run_agent_analysis(
    request: Request,
    payload: AgentRequest,
    background_tasks: BackgroundTasks,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_async_session)],
):
    """Queue the full agentic workflow (202 + poll); runs inline only if Redis is down."""
    result = await session.exec(
        select(Resume).where(Resume.id == payload.resume_id, Resume.user_id == current_user.id)
    )
    resume = result.first()
    if not resume:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resume not found")
    if not resume.raw_text:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Resume has no extracted text"
        )

    task_id = await task_state.create("agent", current_user.id, steps=list(_AGENT_STEPS))
    if task_id:
        background_tasks.add_task(
            _run_agent_bg, task_id, str(payload.job_url), resume.raw_text, str(current_user.id)
        )
        return JSONResponse(
            status_code=status.HTTP_202_ACCEPTED,
            content={"task_id": task_id, "status": "PENDING"},
        )

    logger.warning("agent running inline — Redis task store unavailable")
    from app.services.agent_graph import run_agent  # noqa: PLC0415

    # to_thread keeps the loop free and gives the tools a loop-less thread to
    # asyncio.run() in — calling run_agent directly here would do neither.
    agent_result = await asyncio.to_thread(
        run_agent,
        job_url=str(payload.job_url),
        resume_text=resume.raw_text,
        user_id=str(current_user.id),
    )
    return AgentResponse(**agent_result)


@router.get("/task/{task_id}")
async def poll_agent_task(
    task_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
):
    """Poll an async agent run — same status contract as the other task polls."""
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
