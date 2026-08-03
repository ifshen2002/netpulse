import asyncio
import json
import uuid
from datetime import datetime, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import text

from db import engine
from redis_client import client as redis
from routers.websocket import manager
from services.alerting import (
    check_heartbeats,
    check_endpoint_heartbeats,
    evaluate as evaluate_alerts,
    evaluate_endpoint,
    reload_rules,
)
from services.chaos import apply_overlay
from services.monitoring import collect as collect_node1
from services.normalization import normalize, normalize_endpoint
from services.probe import get_window_seconds, run_probe
from services.simulator import get_burst_interval, generate as generate_synthetic

scheduler = AsyncIOScheduler()
_started = False

# ── V2 endpoint status tracking ──────────────────────────────────
_endpoint_status: dict[str, str] = {}


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
        # Resolve project_id from nodes (seeded data — one project owns all nodes).
        pid_rows = (await conn.execute(
            text("SELECT id, project_id FROM nodes WHERE project_id IS NOT NULL ORDER BY id")
        )).fetchall()
        node_projects = {r[0]: r[1] for r in pid_rows}

        for m in normalized:
            pid = node_projects.get(m["node_id"])
            await conn.execute(
                text(
                    "INSERT INTO metrics (node_id, timestamp, cpu, memory, disk, "
                    "latency_ms, packet_loss_pct, status, project_id) "
                    "VALUES (:node_id, :ts, :cpu, :memory, :disk, "
                    ":latency_ms, :packet_loss_pct, :status, :project_id)"
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
                    "project_id": pid,
                },
            )

    for m in normalized:
        await redis.set(
            f"metrics:latest:{m['node_id']}",
            json.dumps(m),
        )


# ── V2 endpoint collection ─────────────────────────────────────


async def _collect_endpoints() -> None:
    async with engine.begin() as conn:
        result = await conn.execute(
            text(
                "SELECT e.id, e.target_host, e.project_id "
                "FROM endpoints e "
                "WHERE e.enabled = true"
            )
        )
        ep_rows = [(row[0], row[1], row[2]) for row in result.fetchall()]

    live_ids = {r[0] for r in ep_rows}

    for prefix in ("metrics:latest:endpoint:", "packet_evidence:latest:"):
        keys = await redis.keys(f"{prefix}*")
        for key in keys:
            key_str = key.decode() if isinstance(key, bytes) else key
            cached_id = key_str.replace(prefix, "")
            if cached_id not in live_ids:
                await redis.delete(key_str)

    if not ep_rows:
        return

    window_s = get_window_seconds()
    ts = datetime.now(timezone.utc)

    tasks = {
        endpoint_id: asyncio.create_task(run_probe(target_host, endpoint_id))
        for endpoint_id, target_host, _ep_project_id in ep_rows
    }
    for task in tasks.values():
        await task

    async with engine.begin() as conn:
        for endpoint_id, target_host, ep_project_id in ep_rows:
            raw = tasks[endpoint_id].result()

            pe_id = str(uuid.uuid4())
            await conn.execute(
                text(
                    "INSERT INTO packet_evidence "
                    "(id, endpoint_id, protocol, src_ip, dst_ip, "
                    "ttl, packet_size_bytes, icmp_seq, rtt_ms, timestamp, raw_output, project_id) "
                    "VALUES (:id, :endpoint_id, :protocol, :src_ip, :dst_ip, "
                    ":ttl, :packet_size_bytes, :icmp_seq, :rtt_ms, :ts, :raw_output, :project_id)"
                ),
                {
                    "id": pe_id,
                    "endpoint_id": endpoint_id,
                    "protocol": raw["protocol"],
                    "src_ip": raw["src_ip"],
                    "dst_ip": raw["dst_ip"],
                    "ttl": raw["ttl"],
                    "packet_size_bytes": raw["packet_size_bytes"],
                    "icmp_seq": raw["icmp_seq"],
                    "rtt_ms": raw["latency_ms"],
                    "ts": ts,
                    "raw_output": raw.get("raw_output", ""),
                    "project_id": ep_project_id,
                },
            )

            raw["packet_evidence_id"] = pe_id
            raw["endpoint_id"] = endpoint_id

            pct_loss, pct_avail, has_data = await _calc_endpoint_window(
                conn, endpoint_id, window_s
            )
            metric = normalize_endpoint(raw, pct_loss, pct_avail, has_data)

            await conn.execute(
                text(
                    "INSERT INTO probe_metrics "
                    "(endpoint_id, packet_evidence_id, timestamp, "
                    "latency_ms, packet_loss_pct, availability_pct, status, project_id) "
                    "VALUES (:endpoint_id, :pe_id, :ts, "
                    ":latency_ms, :packet_loss_pct, :availability_pct, :status, :project_id)"
                ),
                {
                    "endpoint_id": metric["endpoint_id"],
                    "pe_id": metric["packet_evidence_id"],
                    "ts": ts,
                    "latency_ms": metric["latency_ms"],
                    "packet_loss_pct": metric["packet_loss_pct"],
                    "availability_pct": metric["availability_pct"],
                    "status": metric["status"],
                    "project_id": ep_project_id,
                },
            )

            await conn.execute(
                text("UPDATE endpoints SET status=:s, last_seen=:ts WHERE id=:id"),
                {"s": metric["status"], "ts": ts, "id": endpoint_id},
            )

            old_status = _endpoint_status.get(endpoint_id)
            if old_status is not None and old_status != metric["status"]:
                await manager.broadcast(json.dumps({
                    "type": "endpoint_status_changed",
                    "endpoint_id": endpoint_id,
                    "status": metric["status"],
                    "previous_status": old_status,
                    "timestamp": ts.isoformat(),
                }))
            _endpoint_status[endpoint_id] = metric["status"]

            await redis.set(
                f"metrics:latest:endpoint:{endpoint_id}",
                json.dumps({**metric, "endpoint": target_host}),
            )
            await redis.set(
                f"packet_evidence:latest:{endpoint_id}",
                json.dumps({
                    "id": pe_id,
                    "endpoint_id": endpoint_id,
                    "endpoint": target_host,
                    "protocol": raw["protocol"],
                    "src_ip": raw["src_ip"],
                    "dst_ip": raw["dst_ip"],
                    "ttl": raw["ttl"],
                    "packet_size_bytes": raw["packet_size_bytes"],
                    "icmp_seq": raw["icmp_seq"],
                    "rtt_ms": raw["latency_ms"],
                    "timestamp": ts.isoformat(),
                    "raw_output": raw.get("raw_output", ""),
                }),
            )


async def _calc_endpoint_window(conn, endpoint_id: str, window_s: int):
    """Return (packet_loss_pct, availability_pct, has_data) for the window."""
    result = await conn.execute(
        text(
            "SELECT COUNT(*), COUNT(*) FILTER (WHERE ttl > 0) "
            "FROM packet_evidence "
            "WHERE endpoint_id = :eid "
            "AND timestamp > NOW() - :window * INTERVAL '1 second'"
        ),
        {"eid": endpoint_id, "window": window_s},
    )
    total, successes = result.fetchone()
    if total == 0:
        return 0.0, 0.0, False
    pct_loss = ((total - successes) / total) * 100
    pct_avail = (successes / total) * 100
    return pct_loss, pct_avail, True


async def _push_endpoint_metrics() -> None:
    if manager.count == 0:
        return

    keys = await redis.keys("metrics:latest:endpoint:*")
    for key in keys:
        raw = await redis.get(key)
        if raw is None:
            continue
        m = json.loads(raw)
        await manager.broadcast(json.dumps({
            "type": "endpoint_metric_update",
            "endpoint_id": m["endpoint_id"],
            "endpoint": m["endpoint"],
            "latency_ms": m["latency_ms"],
            "packet_loss_pct": m["packet_loss_pct"],
            "availability_pct": m["availability_pct"],
            "status": m["status"],
            "timestamp": m["timestamp"],
        }))

    pkeys = await redis.keys("packet_evidence:latest:*")
    for key in pkeys:
        raw = await redis.get(key)
        if raw is None:
            continue
        pe = json.loads(raw)
        await manager.broadcast(json.dumps({
            "type": "packet_evidence",
            "evidence_id": pe["id"],
            "endpoint_id": pe["endpoint_id"],
            "endpoint": pe["endpoint"],
            "protocol": pe["protocol"],
            "src_ip": pe["src_ip"],
            "dst_ip": pe["dst_ip"],
            "ttl": pe["ttl"],
            "packet_size_bytes": pe["packet_size_bytes"],
            "icmp_seq": pe["icmp_seq"],
            "rtt_ms": pe["rtt_ms"],
            "timestamp": pe["timestamp"],
            "raw_output": pe.get("raw_output", ""),
        }))


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
        await conn.execute(
            text("DELETE FROM probe_metrics WHERE timestamp < NOW() - INTERVAL '72 hours'")
        )
        await conn.execute(
            text("DELETE FROM packet_evidence WHERE timestamp < NOW() - INTERVAL '72 hours'")
        )


async def _evaluate_alerts() -> None:
    for node_id in ("node-1", "node-2", "node-3"):
        await evaluate_alerts(node_id)


async def _evaluate_endpoint_alerts() -> None:
    async with engine.begin() as conn:
        result = await conn.execute(text("SELECT id FROM endpoints"))
        endpoint_ids = [row[0] for row in result.fetchall()]
    for endpoint_id in endpoint_ids:
        await evaluate_endpoint(endpoint_id)


async def _check_heartbeats_job() -> None:
    await check_heartbeats()


async def _check_endpoint_heartbeats_job() -> None:
    await check_endpoint_heartbeats()


async def _reload_rules_startup() -> None:
    await reload_rules()


async def _backfill_project_ids() -> None:
    """Backfill seeded resources with NULL project_id to the first project."""
    from sqlalchemy import text as _text
    async with engine.begin() as conn:
        row = (await conn.execute(
            _text("SELECT id FROM projects ORDER BY created_at LIMIT 1")
        )).fetchone()
        if row is None:
            return
        project_id = row[0]
        for table in (
            "nodes", "metrics", "alerts", "incidents", "chaos_events",
            "endpoints", "probe_metrics", "alert_rules", "packet_evidence",
        ):
            await conn.execute(
                _text(f"UPDATE {table} SET project_id = :pid WHERE project_id IS NULL"),
                {"pid": project_id},
            )


def start_scheduler() -> None:
    global _started
    if not _started:
        scheduler.add_job(_reload_rules_startup, id="reload_rules_startup")
        scheduler.add_job(_backfill_project_ids, id="backfill_startup")
        scheduler.add_job(_collect_all_nodes, "interval", seconds=5, id="collect_metrics")
        scheduler.add_job(_collect_endpoints, "interval", seconds=5, id="collect_endpoints")
        scheduler.add_job(_push_metrics, "interval", seconds=1, id="push_metrics")
        scheduler.add_job(_push_endpoint_metrics, "interval", seconds=1, id="push_endpoint_metrics")
        scheduler.add_job(_evaluate_alerts, "interval", seconds=5, id="evaluate_alerts")
        scheduler.add_job(_evaluate_endpoint_alerts, "interval", seconds=5, id="evaluate_endpoint_alerts")
        scheduler.add_job(_check_heartbeats_job, "interval", seconds=15, id="check_heartbeats")
        scheduler.add_job(
            _check_endpoint_heartbeats_job, "interval", seconds=15, id="check_endpoint_heartbeats"
        )
        scheduler.add_job(_backfill_project_ids, "interval", seconds=30, id="backfill_project_ids")
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
