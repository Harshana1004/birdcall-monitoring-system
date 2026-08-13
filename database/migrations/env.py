from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from alembic import context
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import (
    async_engine_from_config,
)


# ============================================================
# Project paths
# ============================================================


PROJECT_ROOT = (
    Path(__file__)
    .resolve()
    .parents[2]
)

BACKEND_DIRECTORY = (
    PROJECT_ROOT
    / "backend"
)


# Add backend/ to the Python import path so that the runtime
# package can be imported exactly as it is by the application:
#
#     from src...
#
# Do NOT import using "backend.src", because doing so would load
# the same modules under a second package name and create a
# separate SQLAlchemy Base instance.
if str(BACKEND_DIRECTORY) not in sys.path:
    sys.path.insert(
        0,
        str(BACKEND_DIRECTORY),
    )


# ============================================================
# Backend configuration / models
# ============================================================


from src.core.config import settings
from src.database import Base

# Import all ORM models so that they are registered with the
# exact same Base.metadata instance used by the application.
from src.models import (
    Detection,
    Device,
    Recording,
)


# ============================================================
# Alembic configuration
# ============================================================


config = context.config


# Use the same PostgreSQL connection URL as the running backend.
config.set_main_option(
    "sqlalchemy.url",
    settings.database_url,
)


target_metadata = (
    Base.metadata
)


# ============================================================
# Offline migrations
# ============================================================


def run_migrations_offline() -> None:
    """
    Run migrations without creating a live database connection.
    """

    url = config.get_main_option(
        "sqlalchemy.url"
    )

    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={
            "paramstyle": "named",
        },
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


# ============================================================
# Online migrations
# ============================================================


def do_run_migrations(
    connection,
) -> None:
    """
    Configure Alembic using an existing synchronous connection
    supplied by SQLAlchemy's async bridge.
    """

    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """
    Run Alembic using the backend's async PostgreSQL driver.
    """

    configuration = (
        config.get_section(
            config.config_ini_section,
            {},
        )
    )

    connectable = (
        async_engine_from_config(
            configuration,
            prefix="sqlalchemy.",
            poolclass=pool.NullPool,
        )
    )

    async with connectable.connect() as connection:
        await connection.run_sync(
            do_run_migrations
        )

    await connectable.dispose()


def run_migrations_online() -> None:
    """
    Entry point for online asynchronous migrations.
    """

    asyncio.run(
        run_async_migrations()
    )


# ============================================================
# Entry point
# ============================================================


if context.is_offline_mode():
    run_migrations_offline()

else:
    run_migrations_online()