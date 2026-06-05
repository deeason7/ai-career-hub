"""RAG management endpoints: stats, semantic search, and reindex."""

import asyncio
import uuid
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api.v1.deps import get_current_user
from app.core.db import get_async_session
from app.models.cover_letter import CoverLetter
from app.models.resume import Resume
from app.models.user import User

router = APIRouter()


class RAGSearchRequest(BaseModel):
    query: str = Field(..., max_length=2000)
    top_k: int = Field(default=6, ge=1, le=20)
    source_types: list[str] | None = None


class RAGSearchResult(BaseModel):
    chunk_text: str
    source_type: str
    source_id: str
    chunk_index: int
    distance: float


@router.get("/stats")
async def rag_stats(
    current_user: Annotated[User, Depends(get_current_user)],
):
    """Return embedding chunk counts for the current user."""
    from app.services.embedding_service import get_embedding_stats  # noqa: PLC0415

    return get_embedding_stats(current_user.id)


@router.post("/search", response_model=list[RAGSearchResult])
async def rag_search(
    payload: RAGSearchRequest,
    current_user: Annotated[User, Depends(get_current_user)],
):
    """Semantic search across the user's embedded documents."""
    from app.services.embedding_service import retrieve_context  # noqa: PLC0415

    if not payload.query.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Query must not be empty.",
        )

    results = await asyncio.to_thread(
        retrieve_context,
        user_id=current_user.id,
        query=payload.query,
        top_k=payload.top_k,
        source_types=payload.source_types,
    )
    return results


def _reindex_bg(user_id: uuid.UUID, documents: list[dict]) -> None:
    """Background task: re-embed all user documents."""
    import logging  # noqa: PLC0415

    from app.services.embedding_service import reindex_all_documents  # noqa: PLC0415

    logger = logging.getLogger(__name__)
    try:
        result = reindex_all_documents(user_id, documents)
        logger.info(
            "Reindex complete for user=%s: %d chunks from %d docs",
            str(user_id)[:8],
            result["total_chunks"],
            result["documents_processed"],
        )
    except Exception as exc:
        logger.error("Reindex failed for user=%s: %s", str(user_id)[:8], exc, exc_info=True)


@router.post("/reindex", status_code=status.HTTP_202_ACCEPTED)
async def rag_reindex(
    background_tasks: BackgroundTasks,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_async_session)],
):
    """Re-embed all of the current user's documents (resumes + cover letters)."""
    documents: list[dict] = []

    result = await session.exec(select(Resume).where(Resume.user_id == current_user.id))
    for resume in result.all():
        if resume.raw_text:
            documents.append(
                {
                    "source_type": "resume",
                    "source_id": str(resume.id),
                    "text": resume.raw_text,
                }
            )

    result = await session.exec(select(CoverLetter).where(CoverLetter.user_id == current_user.id))
    for cl in result.all():
        if cl.generated_text:
            documents.append(
                {
                    "source_type": "cover_letter",
                    "source_id": str(cl.id),
                    "text": cl.generated_text,
                }
            )
        if cl.job_description:
            documents.append(
                {
                    "source_type": "job_description",
                    "source_id": str(cl.id),
                    "text": cl.job_description,
                }
            )

    if not documents:
        return {"status": "no_documents", "message": "No documents found to reindex."}

    background_tasks.add_task(_reindex_bg, current_user.id, documents)
    return {
        "status": "reindexing",
        "documents_queued": len(documents),
        "message": "Reindex started in background.",
    }
