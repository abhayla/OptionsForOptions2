"""Async Alembic environment (the `alembic init -t async` shape).

Adapted from abhayla/algochanakya@bf9faf7:backend/alembic/env.py (ADR-047): that env was sync (it rewrote the asyncpg
URL to psycopg2); this one runs migrations on an async connection. Models are imported explicitly so autogenerate
sees them. Run as the OWNER role, never as the application role (migration 0001 refuses the application role).

The URL comes from ALEMBIC_DATABASE_URL, else DATABASE_URL (owner credentials, from the environment only).
"""

from __future__ import annotations

import asyncio
import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

import ofo_app.models  # noqa: F401  explicit model import (legacy rule: autogenerate is blind without it)
from ofo_app.db import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _url() -> str:
    url = os.environ.get("ALEMBIC_DATABASE_URL") or os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("set ALEMBIC_DATABASE_URL (or DATABASE_URL) to the owner role's PostgreSQL URL")
    return url


def run_migrations_offline() -> None:
    context.configure(
        url=_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata, transaction_per_migration=True)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    section = config.get_section(config.config_ini_section, {})
    section["sqlalchemy.url"] = _url()
    connectable = async_engine_from_config(section, prefix="sqlalchemy.", poolclass=pool.NullPool)
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
