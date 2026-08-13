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


if str(BACKEND_DIRECTORY) not in sys.path:
    sys.path.insert(
        0,
        str(BACKEND_DIRECTORY),
    )


# ============================================================
# Backend configuration / models
# ============================================================


from backend.src.core.config import settings
from backend.src.database import Base

# Import ORM models so they are registered in Base.metadata.
from backend.src.models import (
    Detection,
    Device,
    Recording,
)


# ============================================================
# Alembic configuration
# ============================================================


config = context.config


# Use the same PostgreSQL URL as the running backend.
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
    url = config.get_main_option(
        "sqlalchemy.url"
    )

    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={
            "paramstyle": "named"
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
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    configuration = (
        config.get_section(
            config.config_ini_section,
            {}
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