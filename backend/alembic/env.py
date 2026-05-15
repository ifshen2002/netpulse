import asyncio
import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy.ext.asyncio import create_async_engine

from db import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

db_url = os.environ.get(
    "DATABASE_URL", "postgresql+asyncpg://netpulse:netpulse@localhost:5432/netpulse"
)
config.set_main_option("sqlalchemy.url", db_url)

target_metadata = Base.metadata


def do_run_migrations(connection):
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online():
    connectable = create_async_engine(db_url)
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_offline():
    context.configure(url=db_url, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
