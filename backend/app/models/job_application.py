import uuid
from datetime import UTC, date, datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Text
from sqlmodel import Column, Field, Relationship, SQLModel

if TYPE_CHECKING:
    from app.models.user import User


class JobApplicationBase(SQLModel):
    company: str = Field(max_length=255)
    role: str = Field(max_length=255)
    job_url: str | None = Field(default=None, max_length=500)
    status: str = Field(default="wishlist", max_length=50)
    notes: str | None = Field(default=None)
    applied_at: datetime | None = Field(default=None)
    deadline: date | None = Field(default=None)


class JobApplication(JobApplicationBase, table=True):
    __tablename__ = "job_applications"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    user_id: uuid.UUID = Field(foreign_key="users.id", index=True)
    notes: str | None = Field(default=None, sa_column=Column(Text))
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    user: Optional["User"] = Relationship(back_populates="job_applications")


class JobApplicationCreate(JobApplicationBase):
    pass


class JobApplicationUpdate(SQLModel):
    company: str | None = None
    role: str | None = None
    job_url: str | None = None
    status: str | None = None
    notes: str | None = None
    applied_at: datetime | None = None
    deadline: date | None = None


class JobApplicationRead(JobApplicationBase):
    id: uuid.UUID
    user_id: uuid.UUID
    created_at: datetime
    updated_at: datetime
