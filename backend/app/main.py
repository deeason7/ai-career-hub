import asyncio
import logging
import uuid
from contextlib import asynccontextmanager

import sentry_sdk
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from sqlalchemy.exc import InterfaceError, OperationalError

from app.api.v1.api import api_router
from app.core.config import settings
from app.core.db import async_engine, create_db_and_tables
from app.core.limiter import limiter

logger = logging.getLogger(__name__)

# Initialise Sentry — no-op when SENTRY_DSN is empty (local / CI)
if settings.SENTRY_DSN:
    sentry_sdk.init(
        dsn=settings.SENTRY_DSN,
        traces_sample_rate=0.1,  # 10% of requests get performance traces
        send_default_pii=False,  # Never send passwords, tokens, or PII
    )


async def _run_migrations_when_db_ready() -> None:
    """Wait for the DB to accept connections, then run alembic upgrade head.

    Runs as a background task so uvicorn starts immediately without waiting
    for RDS. Retries every 5s for up to 10 minutes.
    """
    from alembic import command as alembic_command
    from alembic.config import Config as AlembicConfig
    from sqlalchemy import text

    MAX_ATTEMPTS = 120  # 120 × 5s = 10 minutes max wait
    loop = asyncio.get_running_loop()
    attempt = 0

    while attempt < MAX_ATTEMPTS:
        try:
            async with async_engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            logger.info(
                "[startup] DB reachable after %d attempt(s) — running alembic upgrade head",
                attempt + 1,
            )
            cfg = AlembicConfig("/app/alembic.ini")
            await loop.run_in_executor(None, alembic_command.upgrade, cfg, "head")
            logger.info("[startup] alembic upgrade head: OK")
            return
        except Exception as exc:
            attempt += 1
            logger.info(
                "[startup] DB not ready (%s, attempt %d/%d) — retrying in 5s",
                type(exc).__name__,
                attempt,
                MAX_ATTEMPTS,
            )
            await asyncio.sleep(5)

    logger.error(
        "[startup] DB unreachable after %d attempts (10 min) — giving up on migrations",
        MAX_ATTEMPTS,
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Create tables in dev; run migrations async in prod."""
    if not settings.PRODUCTION:
        await create_db_and_tables()
    else:
        asyncio.create_task(_run_migrations_when_db_ready())
    yield


# Show docs only in development (hide attack surface in prod)
_docs_url = "/docs" if not settings.PRODUCTION else None
_redoc_url = "/redoc" if not settings.PRODUCTION else None

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description=(
        "AI Career Hub API — resume management, cover letter generation, "
        "ATS scoring, skill gap analysis, and job application tracking."
    ),
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    docs_url=_docs_url,
    redoc_url=_redoc_url,
    lifespan=lifespan,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

app.include_router(api_router, prefix=settings.API_V1_STR)


# Return a clean 503 with Retry-After during DB cold-start.


@app.exception_handler(OperationalError)
@app.exception_handler(InterfaceError)
async def db_unavailable_handler(request: Request, exc: Exception) -> JSONResponse:
    """Convert SQLAlchemy connection errors into a user-friendly 503."""
    logger.warning(
        "[db] Connection error on %s %s: %s",
        request.method,
        request.url.path,
        type(exc).__name__,
    )
    return JSONResponse(
        status_code=503,
        content={"detail": "Database is starting up. Please try again in 30 seconds."},
        headers={"Retry-After": "30"},
    )


@app.middleware("http")
async def add_request_id(request: Request, call_next) -> Response:
    """Attach a correlation ID to every request and echo it in the response.

    Reads X-Request-ID from the incoming request (set by nginx or the client)
    or generates a fresh UUID. The ID is returned on every response so clients
    and Sentry can correlate logs across services.
    """
    request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response


@app.middleware("http")
async def add_security_headers(request: Request, call_next) -> Response:
    """Inject security headers on every response."""
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
    if settings.PRODUCTION:
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    # Streamlit requires 'unsafe-inline' for scripts and styles.
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline'; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data:; "
        "connect-src 'self'; "
        "frame-ancestors 'none';"
    )
    return response


@app.get("/", tags=["Health"])
async def root():
    return {
        "service": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "status": "healthy",
        "docs": "/docs" if not settings.PRODUCTION else None,
    }


@app.get("/health", tags=["Health"])
async def health():
    return {"status": "ok"}
