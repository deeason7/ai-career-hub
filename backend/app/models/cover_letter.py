import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Text
from sqlmodel import Column, Field, Relationship, SQLModel

if TYPE_CHECKING:
    from app.models.resume import Resume
    from app.models.user import User


class CoverLetterBase(SQLModel):
    job_description: str = Field(sa_column=Column(Text))
    ats_score: Optional[float] = Field(default=None)


class CoverLetter(CoverLetterBase, table=True):
    __tablename__ = "cover_letters"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    user_id: uuid.UUID = Field(foreign_key="users.id", index=True)
    resume_id: uuid.UUID = Field(foreign_key="resumes.id", index=True)
    generated_text: Optional[str] = Field(default=None, sa_column=Column(Text))
    task_id: Optional[str] = Field(default=None, max_length=255)  # Celery task ID
    status: str = Field(default="pending", max_length=50)  # pending|processing|success|failure
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # Relationships
    user: Optional["User"] = Relationship(back_populates="cover_letters")
    resume: Optional["Resume"] = Relationship(back_populates="cover_letters")


class CoverLetterCreate(SQLModel):
    job_description: str
    resume_id: Optional[uuid.UUID] = None  # If None, uses the user's active resume


class CoverLetterRead(CoverLetterBase):
    id: uuid.UUID
    user_id: uuid.UUID
    resume_id: uuid.UUID
    generated_text: Optional[str]
    task_id: Optional[str]
    status: str
    created_at: datetime
