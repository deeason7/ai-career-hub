import uuid
from datetime import datetime, timezone
from typing import Optional, TYPE_CHECKING
from sqlmodel import Field, SQLModel, Relationship, Column
from sqlalchemy import Text

if TYPE_CHECKING:
    from app.models.user import User


class JobApplicationBase(SQLModel):
    company: str = Field(max_length=255)
    role: str = Field(max_length=255)
    job_url: Optional[str] = Field(default=None, max_length=500)
    status: str = Field(default="wishlist", max_length=50)
    # Status: wishlist | applied | phone_screen | interview | offer | rejected | accepted
    notes: Optional[str] = Field(default=None, sa_column=Column(Text))
    applied_at: Optional[datetime] = Field(default=None)


class JobApplication(JobApplicationBase, table=True):
    __tablename__ = "job_applications"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    user_id: uuid.UUID = Field(foreign_key="users.id", index=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    user: Optional["User"] = Relationship(back_populates="job_applications")


class JobApplicationCreate(JobApplicationBase):
    pass


class JobApplicationUpdate(SQLModel):
    company: Optional[str] = None
    role: Optional[str] = None
    job_url: Optional[str] = None
    status: Optional[str] = None
    notes: Optional[str] = None
    applied_at: Optional[datetime] = None


class JobApplicationRead(JobApplicationBase):
    id: uuid.UUID
    user_id: uuid.UUID
    created_at: datetime
    updated_at: datetime
