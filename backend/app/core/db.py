from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool
from sqlmodel import SQLModel, create_engine

from app.core.config import settings

# Async engine — NullPool: no client-side pooling.
# Supabase Supavisor (port 6543) handles connection pooling server-side.
# This is the correct pattern for Render free tier (spin-down/spin-up cycles)
# because there are no stale pool connections to recover on wake-up.
#
# prepare_threshold=0 disables prepared statements (int, not URL string).
# Required for Supabase Supavisor/PgBouncer in transaction mode — passing it
# as a URL query param causes a TypeError because psycopg receives it as str.
async_engine = create_async_engine(
    settings.SQLALCHEMY_ASYNC_DATABASE_URI,
    poolclass=NullPool,
    # prepare_threshold=None fully disables prepared statements.
    # prepare_threshold=0 (our previous value) means "prepare on first execution"
    # which still sends PREPARE statements — unsupported by Supabase Supavisor
    # (PgBouncer in transaction mode). None = never prepare = correct for poolers.
    connect_args={"prepare_threshold": None},
)

# Sync engine — used by Alembic (startup) AND cover letter BackgroundTask.
# The background task holds a connection for the entire LLM call (30-60s),
# so pool_size=1 would starve any concurrent sync DB access.
# pool_size=3, max_overflow=5 allows concurrent background tasks + migrations.
# prepare_threshold=None: disable psycopg3 prepared statements — same reason
# as async engine (Supavisor incompatibility; direct port 5432 is fine but
# keeps the config consistent and avoids DuplicatePreparedStatement if ever
# switched back to Supavisor).
_sync_pool_kwargs = dict(
    pool_pre_ping=True,
    pool_size=3,
    max_overflow=5,
    pool_recycle=1800,
    connect_args={"prepare_threshold": None},
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
