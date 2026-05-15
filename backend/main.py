from contextlib import asynccontextmanager

from fastapi import FastAPI

from db import check_db, close_db
from redis_client import check_redis, close_redis
from scheduler import start_scheduler, stop_scheduler


@asynccontextmanager
async def lifespan(app: FastAPI):
    await check_db()
    await check_redis()
    start_scheduler()
    yield
    stop_scheduler()
    await close_redis()
    await close_db()


app = FastAPI(lifespan=lifespan)


@app.get("/api/health")
async def healthcheck():
    db_ok = await check_db()
    redis_ok = await check_redis()
    return {
        "success": True,
        "data": {
            "db": "connected" if db_ok else "disconnected",
            "redis": "connected" if redis_ok else "disconnected",
        },
    }
