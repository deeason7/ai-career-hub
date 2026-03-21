"""
Async AI Task Definitions

These tasks are dispatched by API endpoints and executed by Celery workers.
On completion, results are written back to the PostgreSQL database.
"""
import uuid
import logging
from app.tasks.celery_app import celery_app
from app.services.cover_letter import generate_cover_letter

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, max_retries=2, default_retry_delay=10)
def generate_cover_letter_task(self, cover_letter_id: str, resume_text: str, job_description: str):
    """
    Async task: Generate a cover letter and persist results to the DB.

    Args:
        cover_letter_id: UUID of the CoverLetter row to update on completion.
        resume_text: Raw resume text.
        job_description: Raw job description text.
    """
    from sqlmodel import Session, select
    from app.core.db import sync_engine
    from app.models.cover_letter import CoverLetter
    from datetime import datetime, timezone

    logger.info(f"Starting cover letter generation for CoverLetter ID: {cover_letter_id}")
    try:
        result = generate_cover_letter(resume_text, job_description)
        cover_letter_text = result["cover_letter"]
        rag_context = result["rag_context"]

        with Session(sync_engine) as session:
            cl = session.get(CoverLetter, uuid.UUID(cover_letter_id))
            if cl:
                cl.generated_text = cover_letter_text
                cl.status = "success"
                session.add(cl)
                session.commit()
                logger.info(f"Cover letter saved. ID: {cover_letter_id}")

        return {
            "cover_letter": cover_letter_text,
            "rag_context": rag_context,
        }
    except Exception as exc:
        logger.error(f"Cover letter task failed: {exc}", exc_info=True)
        try:
            from sqlmodel import Session
            from app.core.db import sync_engine
            from app.models.cover_letter import CoverLetter
            with Session(sync_engine) as session:
                cl = session.get(CoverLetter, uuid.UUID(cover_letter_id))
                if cl:
                    cl.status = "failure"
                    session.add(cl)
                    session.commit()
        except Exception:
            pass
        raise self.retry(exc=exc)
