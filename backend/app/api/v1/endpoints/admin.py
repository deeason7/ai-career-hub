"""Admin and lifecycle management endpoints."""

import hmac
import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, status

from app.core.config import settings
from app.core.db import sync_engine
from app.services.lifecycle import reap_stuck_cover_letters, run_lifecycle_cleanup

logger = logging.getLogger(__name__)

router = APIRouter()


def _verify_admin_secret(x_admin_secret: Annotated[str | None, Header()] = None) -> None:
    expected = settings.ADMIN_SECRET
    if not expected or not x_admin_secret or not hmac.compare_digest(x_admin_secret, expected):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden.")


@router.post("/lifecycle/run", dependencies=[Depends(_verify_admin_secret)])
def trigger_lifecycle_cleanup() -> dict:
    """Run the document lifecycle cleanup. Requires X-Admin-Secret header."""
    try:
        result = run_lifecycle_cleanup(sync_engine)
        reaped = reap_stuck_cover_letters(sync_engine)
    except Exception as exc:
        # The nightly cron is the only caller, and a bare 500 tells it nothing —
        # name the failure class so the run log says whether the database was
        # unreachable or a row refused to delete. Message stays out of the
        # response; the full traceback goes to the logs.
        logger.exception("Lifecycle cleanup failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Lifecycle cleanup failed: {type(exc).__name__}",
        ) from exc
    logger.info("Admin-triggered lifecycle cleanup: %s (reaped %d stuck)", result, reaped)
    return {"status": "ok", **result, "reaped_stuck_cover_letters": reaped}
