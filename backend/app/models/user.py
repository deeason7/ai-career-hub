import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlmodel import Field, Relationship, SQLModel

if TYPE_CHECKING:
    from app.models.cover_letter import CoverLetter
    from app.models.job_application import JobApplication
    from app.models.resume import Resume


class UserBase(SQLModel):
    email: str = Field(unique=True, index=True, max_length=255)
    full_name: str | None = Field(default=None, max_length=255)
    role: str = Field(default="candidate")
    is_active: bool = Field(default=True)


class User(UserBase, table=True):
    __tablename__ = "users"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    hashed_password: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    # Relationships
    resumes: list["Resume"] = Relationship(back_populates="user")
    cover_letters: list["CoverLetter"] = Relationship(back_populates="user")
    job_applications: list["JobApplication"] = Relationship(back_populates="user")


class UserCreate(UserBase):
    password: str = Field(min_length=8, description="Minimum 8 characters")


class UserRead(UserBase):
    id: uuid.UUID
    created_at: datetime
