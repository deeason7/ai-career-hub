from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlmodel import SQLModel, Session, create_engine

from app.core.config import settings

# --- Synchronous engine (for Alembic migrations & Celery workers) ---
sync_engine = create_engine(
    settings.SQLALCHEMY_DATABASE_URI,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10,
)

# --- Async engine (for FastAPI endpoints) ---
async_engine = create_async_engine(
    settings.SQLALCHEMY_ASYNC_DATABASE_URI,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10,
)

AsyncSessionLocal = async_sessionmaker(
    bind=async_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_async_session():
    async with AsyncSessionLocal() as session:
        yield session


async def create_db_and_tables():
    """Create all tables (dev only). Use Alembic migrations in production."""
    import app.models  # noqa: F401 — ensures all models are registered
    async with async_engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
