import os

import redis.asyncio as aioredis

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

client: aioredis.Redis = aioredis.Redis.from_url(REDIS_URL)


async def check_redis() -> bool:
    try:
        await client.ping()
        return True
    except Exception:
        return False


async def close_redis() -> None:
    await client.aclose()
