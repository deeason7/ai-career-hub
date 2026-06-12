import json
import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Column, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlmodel import Field, Relationship, SQLModel

if TYPE_CHECKING:
    from app.models.cover_letter import CoverLetter


class CoverLetterRevision(SQLModel, table=True):
    __tablename__ = "cover_letter_revisions"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    cover_letter_id: uuid.UUID = Field(
        sa_column=Column(
            PGUUID(as_uuid=True),
            ForeignKey("cover_letters.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        )
    )
    version_number: int
    # Lineage: the revision this one was refined from. NULL = refined from the
    # letter's active text. SET NULL so deleting an ancestor never blocks.
    parent_revision_id: uuid.UUID | None = Field(
        default=None,
        sa_column=Column(
            PGUUID(as_uuid=True),
            ForeignKey(
                "cover_letter_revisions.id",
                ondelete="SET NULL",
                name="fk_cl_revision_parent",
            ),
            nullable=True,
        ),
    )
    generated_text: str = Field(sa_column=Column(Text))
    user_command: str = Field(sa_column=Column(Text))
    qa_score_honesty: int | None = Field(default=None)
    qa_score_tone: int | None = Field(default=None)
    qa_flags: str | None = Field(default=None, sa_column=Column(Text))
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    cover_letter: Optional["CoverLetter"] = Relationship(back_populates="revisions")

    def set_qa_flags(self, flags: list[str]) -> None:
        self.qa_flags = json.dumps(flags) if flags else None

    def get_qa_flags(self) -> list[str]:
        if not self.qa_flags:
            return []
        return json.loads(self.qa_flags)


class CoverLetterRevisionCreate(SQLModel):
    command: str = Field(..., min_length=3, max_length=1000)
    # Refine from this revision's text instead of the active letter.
    base_version: int | None = Field(default=None, ge=1)


class CoverLetterRevisionRead(SQLModel):
    id: uuid.UUID
    cover_letter_id: uuid.UUID
    version_number: int
    parent_revision_id: uuid.UUID | None = None
    generated_text: str
    user_command: str
    qa_score_honesty: int | None = None
    qa_score_tone: int | None = None
    qa_flags: str | None = None
    created_at: datetime
