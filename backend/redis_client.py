import os

import redis.asyncio as aioredis

REDIS_URL = os.environ.get("REDIS_URL")
if not REDIS_URL:
    raise RuntimeError(
        "REDIS_URL environment variable is required. "
        "Copy .env.example to .env and fill in the values."
    )

# single_connection_client=True: creates a fresh connection per operation
# instead of pooling. Required for pytest-asyncio strict mode where
# each test gets a new event loop (pooled connections from a prior
# loop would be stale). Same rationale as NullPool in db.py.
client: aioredis.Redis = aioredis.Redis.from_url(
    REDIS_URL,
    single_connection_client=True,
)


async def check_redis() -> bool:
    try:
        await client.ping()
        return True
    except Exception:
        return False


async def close_redis() -> None:
    await client.aclose()
