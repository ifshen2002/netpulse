import json
from datetime import datetime, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import text

from db import engine
from redis_client import client as redis
from services.monitoring import collect as collect_node1
from services.normalization import normalize
from services.simulator import generate as generate_synthetic

scheduler = AsyncIOScheduler()
_started = False


async def _collect_all_nodes() -> None:
    raw_metrics = [
        collect_node1(),
        generate_synthetic("node-2"),
        generate_synthetic("node-3"),
    ]

    normalized = []
    for raw in raw_metrics:
        if raw is None:
            continue
        m = normalize(raw)
        # Chaos overlay slot — Phase 5 inserts apply_overlay() here
        normalized.append(m)

    if not normalized:
        return

    ts = datetime.now(timezone.utc)
    async with engine.begin() as conn:
        for m in normalized:
            await conn.execute(
                text(
                    "INSERT INTO metrics (node_id, timestamp, cpu, memory, disk, "
                    "latency_ms, packet_loss_pct, status) "
                    "VALUES (:node_id, :ts, :cpu, :memory, :disk, :latency_ms, :packet_loss_pct, :status)"
                ),
                {
                    "node_id": m["node_id"],
                    "ts": ts,
                    "cpu": m["cpu"],
                    "memory": m["memory"],
                    "disk": m["disk"],
                    "latency_ms": m["latency_ms"],
                    "packet_loss_pct": m["packet_loss_pct"],
                    "status": m["status"],
                },
            )

    for m in normalized:
        await redis.set(
            f"metrics:latest:{m['node_id']}",
            json.dumps(m),
        )


async def _cleanup_retention() -> None:
    async with engine.begin() as conn:
        await conn.execute(
            text("DELETE FROM metrics WHERE timestamp < NOW() - INTERVAL '72 hours'")
        )


def start_scheduler() -> None:
    global _started
    if not _started:
        scheduler.add_job(_collect_all_nodes, "interval", seconds=5, id="collect_metrics")
        scheduler.add_job(_cleanup_retention, "interval", hours=1, id="cleanup_retention")
        scheduler.start()
        _started = True


def stop_scheduler() -> None:
    global _started
    if _started and scheduler.running:
        scheduler.shutdown(wait=False)
        _started = False
