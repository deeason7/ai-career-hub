"""Init file — import all models here so Alembic auto-detects them."""
from app.models.user import User
from app.models.resume import Resume
from app.models.cover_letter import CoverLetter
from app.models.job_application import JobApplication

__all__ = ["User", "Resume", "CoverLetter", "JobApplication"]
