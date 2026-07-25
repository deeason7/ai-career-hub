import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Text
from sqlmodel import Column, Field, Relationship, SQLModel

if TYPE_CHECKING:
    from app.models.cover_letter import CoverLetter
    from app.models.user import User


class ResumeBase(SQLModel):
    name: str = Field(max_length=255)  # User-defined label e.g. "SWE Resume 2026"
    original_filename: str = Field(max_length=255)
    is_active: bool = Field(default=False)


class Resume(ResumeBase, table=True):
    __tablename__ = "resumes"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    user_id: uuid.UUID = Field(foreign_key="users.id", index=True)
    raw_text: str = Field(sa_column=Column(Text))  # Full plain text extracted
    parsed_json: str | None = Field(
        default=None, sa_column=Column(Text)
    )  # JSON string of structured data
    is_permanent: bool = Field(default=False)
    expires_at: datetime | None = Field(default=None)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    # Relationships
    user: Optional["User"] = Relationship(back_populates="resumes")
    # A cover letter cannot outlive its resume — resume_id is NOT NULL, and the
    # default "unlink the children" behaviour would try to null it. This FK has
    # no ON DELETE rule, so the ORM has to delete the letters itself.
    cover_letters: list["CoverLetter"] = Relationship(
        back_populates="resume",
        sa_relationship_kwargs={"cascade": "all, delete"},
    )


class ResumeCreate(SQLModel):
    name: str


class ResumeRead(ResumeBase):
    id: uuid.UUID
    user_id: uuid.UUID
    is_permanent: bool
    expires_at: datetime | None = None
    created_at: datetime
    parsed_json: str | None = None


class ResumeReadWithText(ResumeRead):
    raw_text: str
