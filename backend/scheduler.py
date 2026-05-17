import json
from datetime import datetime, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import text

from db import engine
from redis_client import client as redis
from routers.websocket import manager
from services.alerting import evaluate as evaluate_alerts, check_heartbeats
from services.chaos import apply_overlay
from services.monitoring import collect as collect_node1
from services.normalization import normalize
from services.simulator import get_burst_interval, generate as generate_synthetic

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
        m = apply_overlay(m)
        if m is None:
            continue
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
                    "VALUES (:node_id, :ts, :cpu, :memory, :disk, "
                    ":latency_ms, :packet_loss_pct, :status)"
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


async def _push_metrics() -> None:
    if manager.count == 0:
        return

    for node_id in ("node-1", "node-2", "node-3"):
        raw = await redis.get(f"metrics:latest:{node_id}")
        if raw is None:
            continue
        m = json.loads(raw)
        event = {
            "type": "metric_update",
            "node_id": m["node_id"],
            "cpu": m["cpu"],
            "memory": m["memory"],
            "disk": m["disk"],
            "latency_ms": m["latency_ms"],
            "packet_loss_pct": m["packet_loss_pct"],
            "status": m["status"],
            "timestamp": m["timestamp"],
        }
        await manager.broadcast(json.dumps(event))


async def _cleanup_retention() -> None:
    async with engine.begin() as conn:
        await conn.execute(
            text("DELETE FROM metrics WHERE timestamp < NOW() - INTERVAL '72 hours'")
        )


async def _evaluate_alerts() -> None:
    for node_id in ("node-1", "node-2", "node-3"):
        await evaluate_alerts(node_id)


async def _check_heartbeats_job() -> None:
    await check_heartbeats()


def start_scheduler() -> None:
    global _started
    if not _started:
        scheduler.add_job(_collect_all_nodes, "interval", seconds=5, id="collect_metrics")
        scheduler.add_job(_push_metrics, "interval", seconds=1, id="push_metrics")
        scheduler.add_job(_evaluate_alerts, "interval", seconds=5, id="evaluate_alerts")
        scheduler.add_job(_check_heartbeats_job, "interval", seconds=15, id="check_heartbeats")
        scheduler.add_job(_cleanup_retention, "interval", hours=1, id="cleanup_retention")
        scheduler.start()
        _started = True


def stop_scheduler() -> None:
    global _started
    if _started and scheduler.running:
        scheduler.shutdown(wait=False)
        _started = False


def sync_burst_interval() -> None:
    if not scheduler.running:
        return
    interval = get_burst_interval()
    if interval > 0:
        scheduler.reschedule_job("collect_metrics", trigger="interval", seconds=interval)
    else:
        scheduler.reschedule_job("collect_metrics", trigger="interval", seconds=5)
