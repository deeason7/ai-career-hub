from contextlib import asynccontextmanager

import sentry_sdk
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.api.v1.api import api_router
from app.core.config import settings
from app.core.db import create_db_and_tables
from app.core.limiter import limiter

# Initialise Sentry — no-op when SENTRY_DSN is empty (local / CI)
if settings.SENTRY_DSN:
    sentry_sdk.init(
        dsn=settings.SENTRY_DSN,
        traces_sample_rate=0.1,   # 10% of requests get performance traces
        send_default_pii=False,   # Never send passwords, tokens, or PII
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: create tables via SQLModel in dev; Alembic owns schema in production."""
    if not settings.PRODUCTION:
        await create_db_and_tables()
    yield


# Show docs only in development (hide attack surface in prod)
_docs_url = "/docs" if not settings.PRODUCTION else None
_redoc_url = "/redoc" if not settings.PRODUCTION else None

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description=(
        "🚀 AI Career Hub API — Multi-resume management, RAG cover letter generation, "
        "ATS scoring, skill gap analysis, interview question generation, and job application tracking."
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


@app.middleware("http")
async def add_security_headers(request: Request, call_next) -> Response:
    """Inject security headers on every response — prevents clickjacking, MIME sniffing, etc."""
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
    response.headers["X-XSS-Protection"] = "1; mode=block"
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
