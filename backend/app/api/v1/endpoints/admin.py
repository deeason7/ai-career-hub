"""Admin and lifecycle management endpoints."""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, status

from app.core.config import settings
from app.core.db import sync_engine
from app.services.lifecycle import run_lifecycle_cleanup

logger = logging.getLogger(__name__)

router = APIRouter()


def _verify_admin_secret(x_admin_secret: Annotated[str | None, Header()] = None) -> None:
    if not settings.ADMIN_SECRET or x_admin_secret != settings.ADMIN_SECRET:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden.")


@router.post("/lifecycle/run", dependencies=[Depends(_verify_admin_secret)])
def trigger_lifecycle_cleanup() -> dict:
    """Run the document lifecycle cleanup. Requires X-Admin-Secret header."""
    result = run_lifecycle_cleanup(sync_engine)
    logger.info("Admin-triggered lifecycle cleanup: %s", result)
    return {"status": "ok", **result}
