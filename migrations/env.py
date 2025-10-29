# migrations/env.py
from __future__ import annotations
import asyncio
import importlib
from logging.config import fileConfig

from alembic import context
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy import pool

from src.config import get_settings
from src.data_base.db import Base

# Alembic config
config = context.config

# MODELS IMPORTS --------------------------------------
def import_all_models() -> None:
    modules = [
        "src.data_base.models",
    ]
    for m in modules:
        importlib.import_module(m)

# --- URLS -------------------------------------------------------------
# Convert async DB URL to sync for Alembic
def to_sync_url(url: str) -> str:
    '''Convert async DB URL to sync for Alembic.'''
    return (
        url
        .replace("postgresql+asyncpg://", "postgresql+psycopg2://")
        .replace("postgresql+pg8003://", "postgresql+psycopg2://")
        .replace("sqlite+aiosqlite://", "sqlite:///")
    )


def resolve_urls() -> tuple[str, str]:
    settings = get_settings()
    sync_url = sync_url = settings.POSTGRES_ALEMBIC_URL or to_sync_url(settings.USER_DB_URL)
    async_url = (
        sync_url
        .replace("+psycopg2", "+asyncpg")
        .replace("+psycopg", "+asyncpg")
    )
    return sync_url, async_url


SYNC_URL, ASYNC_URL = resolve_urls()

# Set the SQLAlchemy URL for Alembic
config.set_main_option("sqlalchemy.url", SYNC_URL)

# Setup logging
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

#  Metadata object for 'autogenerate' support
import_all_models()
target_metadata = Base.metadata

# Helper to get 'sql_url' from x-arguments
def _get_x_sql_url() -> str | None:
    x = context.get_x_argument(as_dictionary=True)
    return x.get("sql_url")

# --- OFFLINE ----------------------------------------------------------
def run_migrations_offline():
    url = _get_x_sql_url() or SYNC_URL
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()

# --- ONLINE -----------------------------------------------------------
def do_run_migrations(connection):
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()

# ASYNC ONLINE -----------------------------------------------------
async def run_migrations_online():
    x_url = _get_x_sql_url()
    if x_url:
        async_url = (
            x_url
            .replace("+psycopg2", "+asyncpg")
            .replace("+psycopg", "+asyncpg")
        )
    else:
        async_url = ASYNC_URL


    connectable: AsyncEngine = create_async_engine(async_url, poolclass=pool.NullPool)

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()

# RUN --------------------------------------------------------------
if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
