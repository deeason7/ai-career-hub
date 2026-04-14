from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlmodel import SQLModel, create_engine

from app.core.config import settings

# Async engine — persistent pool talking directly to RDS.
# pool_pre_ping re-validates connections that may have been idle across
# the 1800s recycle window; prevents "SSL connection has been closed" errors
# on the first request after quiet periods.
async_engine = create_async_engine(
    settings.SQLALCHEMY_ASYNC_DATABASE_URI,
    pool_size=5,
    max_overflow=10,
    pool_pre_ping=True,
    pool_recycle=1800,
)

# Sync engine — Alembic migrations and synchronous background tasks
# (e.g. cover letter generation, which holds a connection for the LLM call).
# pool_size=3 is enough for our expected concurrency; max_overflow gives
# headroom during brief traffic spikes without starving the async pool.
_sync_pool_kwargs = dict(
    pool_pre_ping=True,
    pool_size=3,
    max_overflow=5,
    pool_recycle=1800,
)
sync_engine = create_engine(settings.SQLALCHEMY_DATABASE_URI, **_sync_pool_kwargs)

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
