import os
from contextlib import asynccontextmanager

from fastapi import FastAPI

from db import check_db, close_db, engine
from redis_client import check_redis, close_redis
from routers.alerts import router as alerts_router
from routers.chaos import router as chaos_router
from routers.incidents import router as incidents_router
from routers.metrics import router as metrics_router
from routers.nodes import router as nodes_router
from routers.websocket import router as websocket_router
from scheduler import start_scheduler, stop_scheduler

_TESTING = os.environ.get("NETPULSE_TESTING", "").lower() in ("1", "true")


async def _close_stale_incidents():
    """Close any open incidents left over from a previous session."""
    from sqlalchemy import text
    async with engine.begin() as conn:
        await conn.execute(
            text("UPDATE incidents SET status='closed', closed_at=NOW() WHERE status='open'")
        )
        await conn.execute(
            text("UPDATE alerts SET resolved_at=NOW() WHERE resolved_at IS NULL")
        )


@asynccontextmanager
async def lifespan(app: FastAPI):
    await check_db()
    await check_redis()
    if not _TESTING:
        await _close_stale_incidents()
        start_scheduler()
    yield
    if not _TESTING:
        stop_scheduler()
    await close_redis()
    await close_db()


app = FastAPI(lifespan=lifespan)

app.include_router(nodes_router)
app.include_router(metrics_router)
app.include_router(websocket_router)
app.include_router(alerts_router)
app.include_router(incidents_router)
app.include_router(chaos_router)


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
