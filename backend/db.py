import os

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import NullPool


class Base(DeclarativeBase):
    pass


DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError(
        "DATABASE_URL environment variable is required. "
        "Copy .env.example to .env and fill in the values."
    )

# NullPool: creates a fresh connection per engine.connect() call instead of
# reusing from a pool. Required for pytest-asyncio strict mode where each
# test gets a new event loop — connections from a legacy pool would be
# bound to a different (already closed) loop and raise "got Future attached
# to a different loop".
#
# Production trade-off: on a single-process uvicorn deployment this adds
# negligible latency (asyncpg connect ≈ 5ms) while eliminating a class
# of flaky test failures. For high-throughput deployments, reinstate the
# pool and use a shared event-loop fixture instead.
engine: AsyncEngine = create_async_engine(
    DATABASE_URL,
    poolclass=NullPool,
    connect_args={"prepared_statement_cache_size": 0},
)


async def check_db() -> bool:
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


async def close_db() -> None:
    await engine.dispose()
