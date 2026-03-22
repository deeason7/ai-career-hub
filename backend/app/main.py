from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.api.v1.api import api_router
from app.core.config import settings
from app.core.db import create_db_and_tables
from app.core.limiter import limiter


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: ensure tables exist (dev only; use Alembic in prod)."""
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
    allow_origins=[
        "https://ai-career-hub-frontend.onrender.com",
        "http://localhost:8501",   # Streamlit local dev
        "http://localhost:3000",   # Future Next.js dev
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

app.include_router(api_router, prefix=settings.API_V1_STR)


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
