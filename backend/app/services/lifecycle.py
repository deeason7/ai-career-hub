"""Document lifecycle: 15-day TTL for resumes (except newest) and cover letters."""

import logging
from datetime import UTC, datetime, timedelta

from sqlmodel import Session, select

logger = logging.getLogger(__name__)

LIFECYCLE_DAYS = 15
# A cover letter still "processing" after this long was orphaned mid-generation
# (deploy/restart or EC2 sleep) — the reaper fails it so clients stop polling forever.
MAX_PROCESSING_MINUTES = 15


def set_resume_expiry(resume, existing_count: int) -> None:
    """Mark resume permanent if it is the user's first; otherwise set a 15-day expiry."""
    if existing_count == 0:
        resume.is_permanent = True
        resume.expires_at = None
    else:
        resume.is_permanent = False
        resume.expires_at = datetime.now(UTC) + timedelta(days=LIFECYCLE_DAYS)


def promote_to_permanent(resume_id, user_id, engine) -> bool:
    """Mark a resume as permanent and clear its expiry.

    Returns True if the resume was found and updated.
    """
    from app.models.resume import Resume  # noqa: PLC0415

    with Session(engine) as session:
        resume = session.get(Resume, resume_id)
        if not resume or resume.user_id != user_id:
            return False
        resume.is_permanent = True
        resume.expires_at = None
        session.add(resume)
        session.commit()
    return True


def set_cover_letter_expiry(cover_letter) -> None:
    """Set a 15-day expiry on a newly created cover letter."""
    cover_letter.expires_at = datetime.now(UTC) + timedelta(days=LIFECYCLE_DAYS)


def run_lifecycle_cleanup(engine) -> dict:
    """Delete expired resumes and cover letters. Returns counts of deleted rows."""
    from app.models.cover_letter import CoverLetter  # noqa: PLC0415
    from app.models.resume import Resume  # noqa: PLC0415

    now = datetime.now(UTC)
    deleted_resumes = 0
    deleted_cover_letters = 0

    with Session(engine) as session:
        expired_resumes = session.exec(
            select(Resume).where(
                Resume.is_permanent.is_(False),
                Resume.expires_at <= now,
            )
        ).all()
        for r in expired_resumes:
            session.delete(r)
            deleted_resumes += 1

        expired_cls = session.exec(select(CoverLetter).where(CoverLetter.expires_at <= now)).all()
        for cl in expired_cls:
            session.delete(cl)
            deleted_cover_letters += 1

        session.commit()

    logger.info(
        "Lifecycle cleanup complete: %d resume(s), %d cover letter(s) deleted.",
        deleted_resumes,
        deleted_cover_letters,
    )
    return {"deleted_resumes": deleted_resumes, "deleted_cover_letters": deleted_cover_letters}


def reap_stuck_cover_letters(engine, max_age_minutes: int = MAX_PROCESSING_MINUTES) -> int:
    """Fail cover letters stuck in 'processing' past the cutoff. Returns the count reaped."""
    from app.models.cover_letter import CoverLetter  # noqa: PLC0415

    cutoff = datetime.now(UTC) - timedelta(minutes=max_age_minutes)
    reaped = 0

    with Session(engine) as session:
        stuck = session.exec(
            select(CoverLetter).where(
                CoverLetter.status == "processing",
                CoverLetter.started_at < cutoff,
            )
        ).all()
        for cl in stuck:
            cl.status = "failure"
            session.add(cl)
            reaped += 1
        session.commit()

    if reaped:
        logger.info("Reaped %d cover letter(s) stuck in processing.", reaped)
    return reaped
