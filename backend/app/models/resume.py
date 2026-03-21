import uuid
from datetime import datetime, timezone
from typing import Optional, TYPE_CHECKING
from sqlmodel import Field, SQLModel, Relationship, Column
from sqlalchemy import Text

if TYPE_CHECKING:
    from app.models.user import User
    from app.models.cover_letter import CoverLetter


class ResumeBase(SQLModel):
    name: str = Field(max_length=255)  # User-defined label e.g. "SWE Resume 2026"
    original_filename: str = Field(max_length=255)
    is_active: bool = Field(default=False)


class Resume(ResumeBase, table=True):
    __tablename__ = "resumes"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    user_id: uuid.UUID = Field(foreign_key="users.id", index=True)
    raw_text: str = Field(sa_column=Column(Text))          # Full plain text extracted
    parsed_json: Optional[str] = Field(default=None, sa_column=Column(Text))  # JSON string of structured data
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # Relationships
    user: Optional["User"] = Relationship(back_populates="resumes")
    cover_letters: list["CoverLetter"] = Relationship(back_populates="resume")


class ResumeCreate(SQLModel):
    name: str


class ResumeRead(ResumeBase):
    id: uuid.UUID
    user_id: uuid.UUID
    created_at: datetime
    parsed_json: Optional[str] = None


class ResumeReadWithText(ResumeRead):
    raw_text: str
