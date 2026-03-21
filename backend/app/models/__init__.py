"""Init file — import all models here so SQLModel/Alembic auto-detects them."""
from app.models.cover_letter import CoverLetter
from app.models.job_application import JobApplication
from app.models.resume import Resume
from app.models.user import User

__all__ = ["User", "Resume", "CoverLetter", "JobApplication"]
