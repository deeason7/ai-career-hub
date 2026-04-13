"""n8n webhook callback endpoint.

Receives results from n8n Cloud after workflow execution. Authenticated via
a shared secret (X-Webhook-Secret header), not JWT — n8n is an internal service.

Flow:
  FastAPI (POST to n8n) → n8n runs workflow → n8n (PUT to /callback) → DB update
"""
import json
import logging
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.db import get_async_session
from app.models.cover_letter import CoverLetter

logger = logging.getLogger(__name__)

router = APIRouter()


class N8nCallbackPayload(BaseModel):
    """Payload sent by n8n after processing a cover letter."""
    generated_text: str = Field(..., min_length=50)
    status: str = Field(default="success", pattern="^(success|failure)$")
    qa_score_honesty: Optional[int] = Field(default=None, ge=1, le=10)
    qa_score_tone: Optional[int] = Field(default=None, ge=1, le=10)
    qa_flags: list[str] = Field(default_factory=list)
    qa_retries: int = Field(default=0, ge=0)
    error_message: Optional[str] = None


def _verify_webhook_secret(x_webhook_secret: str = Header(...)) -> str:
    """Validate that the request comes from our n8n instance."""
    if not settings.N8N_WEBHOOK_SECRET:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="n8n webhook not configured.",
        )
    if x_webhook_secret != settings.N8N_WEBHOOK_SECRET:
        logger.warning("Invalid webhook secret received")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid webhook secret.",
        )
    return x_webhook_secret


@router.put(
    "/cover-letters/{cover_letter_id}/callback",
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(_verify_webhook_secret)],
)
async def n8n_cover_letter_callback(
    cover_letter_id: uuid.UUID,
    payload: N8nCallbackPayload,
    session: AsyncSession = Depends(get_async_session),
):
    """Receive cover letter results from n8n workflow.

    Authenticated via X-Webhook-Secret header (shared secret, not JWT).
    Updates the CoverLetter record in the database with generated text and QA scores.
    """
    cl = await session.get(CoverLetter, cover_letter_id)
    if not cl:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Cover letter not found.",
        )

    if cl.status != "processing":
        logger.warning(
            "n8n callback for %s but status is '%s' (not 'processing')",
            cover_letter_id, cl.status,
        )
        return {"status": "ignored", "reason": f"Cover letter already in state '{cl.status}'"}

    cl.generated_text = payload.generated_text
    cl.status = payload.status
    cl.qa_retries = payload.qa_retries

    if payload.qa_score_honesty is not None:
        cl.qa_score_honesty = payload.qa_score_honesty
    if payload.qa_score_tone is not None:
        cl.qa_score_tone = payload.qa_score_tone
    if payload.qa_flags:
        cl.set_qa_flags(payload.qa_flags)

    if payload.status == "failure" and payload.error_message:
        logger.error("n8n reported failure for %s: %s", cover_letter_id, payload.error_message)

    session.add(cl)
    await session.commit()
    await session.refresh(cl)

    logger.info(
        "n8n callback processed for %s: status=%s, honesty=%s",
        cover_letter_id, cl.status, cl.qa_score_honesty,
    )
    return {"status": "updated", "cover_letter_id": str(cover_letter_id)}
