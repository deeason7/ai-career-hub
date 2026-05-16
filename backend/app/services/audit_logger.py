"""Fire-and-forget audit event logging (OWASP A09 compliance)."""

import hashlib
import json
import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy import Column, Text
from sqlmodel import Field, Session, SQLModel

from app.core.db import sync_engine

logger = logging.getLogger(__name__)


class AuditLog(SQLModel, table=True):
    __tablename__ = "audit_logs"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    user_id: uuid.UUID | None = Field(default=None, index=True)
    event: str = Field(max_length=100)
    ip_hash: str | None = Field(default=None, max_length=64)
    # "metadata" is reserved by SQLAlchemy's Declarative API — use "event_metadata"
    # as the Python attribute; the DB column stays named "metadata" via sa_column.
    event_metadata: str | None = Field(
        default=None, sa_column=Column("metadata", Text(), nullable=True)
    )
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


def _hash_ip(ip: str) -> str:
    """Return SHA-256 hex digest of the raw IP address. Never store the plaintext IP."""
    return hashlib.sha256(ip.encode()).hexdigest()


def emit(
    event: str,
    *,
    user_id: uuid.UUID | None = None,
    request=None,
    metadata: dict | None = None,
) -> None:
    """Write one audit record. Never raises — failures are logged and swallowed."""
    try:
        ip_hash = None
        if request is not None:
            raw_ip = request.client.host if request.client else None
            if raw_ip:
                ip_hash = _hash_ip(raw_ip)

        meta_str = json.dumps(metadata) if metadata else None

        log = AuditLog(
            user_id=user_id,
            event=event,
            ip_hash=ip_hash,
            event_metadata=meta_str,
        )
        with Session(sync_engine) as session:
            session.add(log)
            session.commit()
    except Exception as exc:  # noqa: BLE001
        logger.warning("audit_logger.emit failed (non-fatal): %s", exc)
