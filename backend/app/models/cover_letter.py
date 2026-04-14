import json
import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Text
from sqlmodel import Column, Field, Relationship, SQLModel

if TYPE_CHECKING:
    from app.models.resume import Resume
    from app.models.user import User


class CoverLetterBase(SQLModel):
    job_description: str
    ats_score: float | None = Field(default=None)


class CoverLetter(CoverLetterBase, table=True):
    __tablename__ = "cover_letters"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    user_id: uuid.UUID = Field(foreign_key="users.id", index=True)
    resume_id: uuid.UUID = Field(foreign_key="resumes.id", index=True)
    job_description: str = Field(sa_column=Column(Text))
    generated_text: str | None = Field(default=None, sa_column=Column(Text))
    task_id: str | None = Field(default=None, max_length=255)
    status: str = Field(default="pending", max_length=50)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    # QA review scores (M1: AI-as-a-Judge)
    qa_score_honesty: int | None = Field(default=None)
    qa_score_tone: int | None = Field(default=None)
    qa_flags: str | None = Field(default=None, sa_column=Column(Text))
    qa_retries: int = Field(default=0)

    # Relationships
    user: Optional["User"] = Relationship(back_populates="cover_letters")
    resume: Optional["Resume"] = Relationship(back_populates="cover_letters")

    def set_qa_flags(self, flags: list[str]) -> None:
        """Serialize QA flags list to JSON for DB storage."""
        self.qa_flags = json.dumps(flags) if flags else None

    def get_qa_flags(self) -> list[str]:
        """Deserialize QA flags from JSON."""
        if not self.qa_flags:
            return []
        return json.loads(self.qa_flags)


class CoverLetterCreate(SQLModel):
    job_description: str
    resume_id: uuid.UUID | None = None  # If None, uses the user's active resume


class CoverLetterRead(CoverLetterBase):
    id: uuid.UUID
    user_id: uuid.UUID
    resume_id: uuid.UUID
    generated_text: str | None
    task_id: str | None
    status: str
    created_at: datetime
    qa_score_honesty: int | None = None
    qa_score_tone: int | None = None
    qa_flags: str | None = None
    qa_retries: int = 0
