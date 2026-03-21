from sqlmodel import SQLModel, create_engine, Session
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from app.core.config import settings

# --- Synchronous engine (for Alembic migrations & Celery workers) ---
sync_engine = create_engine(
    settings.SQLALCHEMY_DATABASE_URI,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
)

# --- Async engine (for FastAPI endpoints) ---
async_engine = create_async_engine(
    settings.SQLALCHEMY_ASYNC_DATABASE_URI,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
)

AsyncSessionLocal = async_sessionmaker(
    bind=async_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_async_session():
    """FastAPI dependency: yields an async DB session."""
    async with AsyncSessionLocal() as session:
        yield session


def get_sync_session():
    """Celery / sync dependency: yields a sync DB session."""
    with Session(sync_engine) as session:
        yield session


async def create_db_and_tables():
    """Create all tables (used in dev/testing). Alembic handles prod migrations."""
    async with async_engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
