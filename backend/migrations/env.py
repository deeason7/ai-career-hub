"""Alembic environment configuration.

Reads the database URL from the app settings so we never hard-code credentials.
Supports synchronous migrations (required by Alembic) even though the app uses
an async engine at runtime.
"""
import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

# ── Make sure `app` is importable from /app (Docker) or backend/ (local) ────
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlmodel import SQLModel  # noqa: E402

import app.models  # noqa: F401,E402  — registers all SQLModel models with metadata
from app.core.config import settings  # noqa: E402

# this is the Alembic Config object
config = context.config

# Inject the real DB URL from settings (overrides the placeholder in alembic.ini)
config.set_main_option("sqlalchemy.url", settings.SQLALCHEMY_DATABASE_URI)

# Interpret the config file for Python logging
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Use SQLModel's metadata so Alembic can detect table changes automatically
target_metadata = SQLModel.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL and not an Engine.
    Useful for generating migration scripts without a live DB connection.
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    Creates an engine and associates a connection with the context.
    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
