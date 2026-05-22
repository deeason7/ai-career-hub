import re
import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import Column, DateTime
from sqlmodel import Field, Relationship, SQLModel

if TYPE_CHECKING:
    from app.models.cover_letter import CoverLetter
    from app.models.job_application import JobApplication
    from app.models.resume import Resume

_EMAIL_RE = re.compile(r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$")


class UserBase(SQLModel):
    email: str = Field(unique=True, index=True, max_length=255)
    full_name: str | None = Field(default=None, max_length=255)
    is_active: bool = Field(default=True)


class User(UserBase, table=True):
    __tablename__ = "users"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    hashed_password: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_column=Column(
            DateTime(timezone=True),
            default=lambda: datetime.now(UTC),
            onupdate=lambda: datetime.now(UTC),
            nullable=False,
        ),
    )

    # Relationships
    resumes: list["Resume"] = Relationship(back_populates="user")
    cover_letters: list["CoverLetter"] = Relationship(back_populates="user")
    job_applications: list["JobApplication"] = Relationship(back_populates="user")


class UserCreate(UserBase):
    password: str = Field(min_length=8, description="Minimum 8 characters")

    @classmethod
    def __get_validators__(cls):
        yield from super().__get_validators__()

    def model_post_init(self, __context) -> None:  # noqa: ANN001
        if not _EMAIL_RE.match(self.email):
            raise ValueError(f"Invalid email address: {self.email!r}")
        pwd = self.password
        if not any(c.isdigit() for c in pwd):
            raise ValueError("Password must contain at least one digit.")
        if not any(not c.islower() for c in pwd):
            raise ValueError("Password must contain at least one uppercase letter or symbol.")
        if pwd.lower() == self.email.lower():
            raise ValueError("Password must not match your email address.")


class UserRead(UserBase):
    id: uuid.UUID
    created_at: datetime
