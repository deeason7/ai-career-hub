from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlmodel import SQLModel, create_engine

from app.core.config import settings

# Supabase free tier has a limited connection pool (Session mode: ~10 clients).
# Two engines (sync + async) × pool_size → keep totals well under that limit.
_pool_kwargs = dict(
    pool_pre_ping=True,   # Detect stale/broken connections before use
    pool_size=2,          # Max idle connections per engine (2 × 2 engines = 4 idle)
    max_overflow=3,       # Burst connections allowed  (up to 5 per engine)
    pool_recycle=1800,    # Recycle connections after 30 min (matches Render spin-down)
)

# --- Synchronous engine (for Alembic migrations & BackgroundTask threads) ---
sync_engine = create_engine(settings.SQLALCHEMY_DATABASE_URI, **_pool_kwargs)

# --- Async engine (for FastAPI endpoints) ---
async_engine = create_async_engine(settings.SQLALCHEMY_ASYNC_DATABASE_URI, **_pool_kwargs)

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
