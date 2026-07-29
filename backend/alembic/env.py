from __future__ import annotations

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import Connection, pool
from sqlalchemy.ext.asyncio import async_engine_from_config

from core.config import settings
from core.db import Base

# Import models so SQLAlchemy registers all table metadata.
import models  # noqa: F401


alembic_config = context.config

alembic_config.set_main_option(
    "sqlalchemy.url",
    settings.database_url.replace("%", "%%"),
)

if alembic_config.config_file_name is not None:
    fileConfig(alembic_config.config_file_name)


target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations without establishing a database connection."""

    database_url = alembic_config.get_main_option("sqlalchemy.url")

    context.configure(
        url=database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_sync_migrations(connection: Connection) -> None:
    """Configure and execute migrations through a synchronous connection."""

    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Create the async engine and run database migrations."""

    connectable = async_engine_from_config(
        alembic_config.get_section(
            alembic_config.config_ini_section,
            {},
        ),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(run_sync_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations using an active database connection."""

    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()