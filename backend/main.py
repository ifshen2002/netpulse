import os
from contextlib import asynccontextmanager

from fastapi import FastAPI

from db import check_db, close_db, engine
from redis_client import check_redis, close_redis
from routers.alert_rules import router as alert_rules_router
from routers.auth import router as auth_router
from routers.alerts import router as alerts_router
from routers.chaos import router as chaos_router
from routers.endpoints import router as endpoints_router
from routers.netchaos import router as netchaos_router
from routers.incidents import router as incidents_router
from routers.metrics import router as metrics_router
from routers.nodes import router as nodes_router
from routers.notifications import router as notifications_router
from routers.websocket import router as websocket_router
from scheduler import start_scheduler, stop_scheduler

_TESTING = os.environ.get("NETPULSE_TESTING", "").lower() in ("1", "true")


_RESOURCE_TABLES = (
    "nodes", "metrics", "alerts", "incidents", "chaos_events",
    "endpoints", "probe_metrics", "alert_rules", "packet_evidence",
)


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


async def _backfill_project_ids():
    """Backfill seeded resources with NULL project_id to the first project.

    Runs before the scheduler starts so initial data collection includes
    correct project_id.  The scheduler also runs a periodic backfill every
    30s as a safety net for any rows that slip through.
    """
    from sqlalchemy import text
    async with engine.begin() as conn:
        row = (await conn.execute(
            text("SELECT id FROM projects ORDER BY created_at LIMIT 1")
        )).fetchone()
        if row is None:
            return
        project_id = row[0]
        for table in _RESOURCE_TABLES:
            await conn.execute(
                text(f"UPDATE {table} SET project_id = :pid WHERE project_id IS NULL"),
                {"pid": project_id},
            )


@asynccontextmanager
async def lifespan(app: FastAPI):
    await check_db()
    await check_redis()
    if not _TESTING:
        await _close_stale_incidents()
        await _backfill_project_ids()
        start_scheduler()
    yield
    if not _TESTING:
        stop_scheduler()
    await close_redis()
    await close_db()


app = FastAPI(lifespan=lifespan)

app.include_router(nodes_router)
app.include_router(metrics_router)
app.include_router(endpoints_router)
app.include_router(websocket_router)
app.include_router(alerts_router)
app.include_router(alert_rules_router)
app.include_router(auth_router)
app.include_router(incidents_router)
app.include_router(notifications_router)
app.include_router(chaos_router)
app.include_router(netchaos_router)


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
