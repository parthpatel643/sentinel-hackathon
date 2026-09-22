import asyncio
import sys
from logging.config import fileConfig
from pathlib import Path
from typing import Literal

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config
from sqlalchemy.sql.schema import SchemaItem

# core_api's own src/ isn't on sys.path when alembic is invoked from the repo
# root by uv's workspace runner; this mirrors how the app itself is packaged.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from core_api.db.base import Base
from core_api.db.models import (  # noqa: F401
    Alert,
    Camera,
    Department,
    Detection,
    Site,
    StreamProfile,
    WatchlistEntry,
)
from sentinel_core.config import get_settings

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# The DB URL comes from Settings (env vars / .env), not a literal in
# alembic.ini — same reasoning as core_api/db/base.py: a combined
# scheme://user:pass@host literal is exactly the shape credential-scanning
# tooling flags and rewrites, and alembic.ini is committed to source control.
_settings = get_settings()
_asyncpg_url = _settings.database_url.replace("postgresql://", "postgresql+asyncpg://", 1)
config.set_main_option("sqlalchemy.url", _asyncpg_url)

target_metadata = Base.metadata

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


ObjectType = Literal[
    "schema",
    "table",
    "column",
    "index",
    "unique_constraint",
    "foreign_key_constraint",
    "check_constraint",
]


def include_object(
    _db_object: SchemaItem,
    name: str | None,
    type_: ObjectType,
    _reflected: bool,
    _compare_to: SchemaItem | None,
) -> bool:
    """PostGIS creates its own `spatial_ref_sys` reference table; without
    this filter, autogenerate would propose dropping it on every diff since
    it isn't one of our declared models — a well-known GeoAlchemy2 + Alembic
    gotcha."""
    return not (type_ == "table" and name == "spatial_ref_sys")


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_object=include_object,
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection, target_metadata=target_metadata, include_object=include_object
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """In this scenario we need to create an Engine
    and associate a connection with the context.

    """

    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""

    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
