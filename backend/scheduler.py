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
    check_probe_heartbeats,
    evaluate as evaluate_alerts,
    evaluate_probe,
    reload_rules,
)
from services.chaos import apply_overlay
from services.monitoring import collect as collect_node1
from services.normalization import normalize, normalize_probe
from services.probe import get_window_seconds, run_probe
from services.simulator import get_burst_interval, generate as generate_synthetic

scheduler = AsyncIOScheduler()
_started = False

# ── V2 link status tracking ──────────────────────────────────
_link_status: dict[str, str] = {}


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


# ── V2 probe collection ─────────────────────────────────────


async def _collect_probes() -> None:
    probe_rows = []

    async with engine.begin() as conn:
        # Primary path: load from endpoints (V2 architecture).
        # Falls back to direct probes query if endpoints table doesn't exist yet.
        try:
            result = await conn.execute(
                text(
                    "SELECT p.id, p.endpoint, l.id AS link_id "
                    "FROM endpoints e "
                    "JOIN probes p ON p.endpoint_id = e.id "
                    "JOIN links l ON l.probe_id = p.id "
                    "WHERE e.enabled = true"
                )
            )
            probe_rows = [(row[0], row[1], row[2]) for row in result.fetchall()]
        except Exception:
            result = await conn.execute(
                text(
                    "SELECT p.id, p.endpoint, l.id AS link_id "
                    "FROM probes p JOIN links l ON l.probe_id = p.id"
                )
            )
            probe_rows = [(row[0], row[1], row[2]) for row in result.fetchall()]

    live_ids = {r[0] for r in probe_rows}

    # Clean up stale Redis keys for probes that no longer exist
    for prefix in ("metrics:latest:probe:", "packet_evidence:latest:"):
        keys = await redis.keys(f"{prefix}*")
        for key in keys:
            key_str = key.decode() if isinstance(key, bytes) else key
            cached_id = key_str.replace(prefix, "")
            if cached_id not in live_ids:
                await redis.delete(key_str)

    if not probe_rows:
        return

    window_s = get_window_seconds()
    ts = datetime.now(timezone.utc)

    tasks = {
        probe_id: asyncio.create_task(run_probe(endpoint, probe_id))
        for probe_id, endpoint, _ in probe_rows
    }
    for task in tasks.values():
        await task

    async with engine.begin() as conn:
        for probe_id, endpoint, link_id in probe_rows:
            raw = tasks[probe_id].result()
            raw["link_id"] = link_id

            pe_id = str(uuid.uuid4())
            await conn.execute(
                text(
                    "INSERT INTO packet_evidence "
                    "(id, probe_id, link_id, protocol, src_ip, dst_ip, "
                    "ttl, packet_size_bytes, icmp_seq, rtt_ms, timestamp, raw_output) "
                    "VALUES (:id, :probe_id, :link_id, :protocol, :src_ip, :dst_ip, "
                    ":ttl, :packet_size_bytes, :icmp_seq, :rtt_ms, :ts, :raw_output)"
                ),
                {
                    "id": pe_id,
                    "probe_id": probe_id,
                    "link_id": link_id,
                    "protocol": raw["protocol"],
                    "src_ip": raw["src_ip"],
                    "dst_ip": raw["dst_ip"],
                    "ttl": raw["ttl"],
                    "packet_size_bytes": raw["packet_size_bytes"],
                    "icmp_seq": raw["icmp_seq"],
                    "rtt_ms": raw["latency_ms"],
                    "ts": ts,
                    "raw_output": raw.get("raw_output", ""),
                },
            )

            raw["packet_evidence_id"] = pe_id

            pct_loss, pct_avail, has_data = await _calc_probe_window(
                conn, probe_id, window_s
            )
            metric = normalize_probe(raw, pct_loss, pct_avail, has_data)

            await conn.execute(
                text(
                    "INSERT INTO probe_metrics "
                    "(probe_id, link_id, packet_evidence_id, timestamp, "
                    "latency_ms, packet_loss_pct, availability_pct, status) "
                    "VALUES (:probe_id, :link_id, :pe_id, :ts, "
                    ":latency_ms, :packet_loss_pct, :availability_pct, :status)"
                ),
                {
                    "probe_id": metric["probe_id"],
                    "link_id": metric["link_id"],
                    "pe_id": metric["packet_evidence_id"],
                    "ts": ts,
                    "latency_ms": metric["latency_ms"],
                    "packet_loss_pct": metric["packet_loss_pct"],
                    "availability_pct": metric["availability_pct"],
                    "status": metric["status"],
                },
            )

            await conn.execute(
                text("UPDATE probes SET status=:s, last_seen=:ts WHERE id=:id"),
                {"s": metric["status"], "ts": ts, "id": probe_id},
            )
            await conn.execute(
                text("UPDATE links SET status=:s, last_seen=:ts WHERE id=:id"),
                {"s": metric["status"], "ts": ts, "id": link_id},
            )

            old_status = _link_status.get(link_id)
            if old_status is not None and old_status != metric["status"]:
                await manager.broadcast(json.dumps({
                    "type": "link_status_changed",
                    "link_id": link_id,
                    "probe_id": probe_id,
                    "status": metric["status"],
                    "previous_status": old_status,
                    "timestamp": ts.isoformat(),
                }))
            _link_status[link_id] = metric["status"]

            await redis.set(
                f"metrics:latest:probe:{probe_id}",
                json.dumps({**metric, "endpoint": endpoint}),
            )
            await redis.set(
                f"packet_evidence:latest:{probe_id}",
                json.dumps({
                    "id": pe_id,
                    "probe_id": probe_id,
                    "link_id": link_id,
                    "endpoint": endpoint,
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


async def _calc_probe_window(conn, probe_id: str, window_s: int):
    """Return (packet_loss_pct, availability_pct, has_data) for the window."""
    result = await conn.execute(
        text(
            "SELECT COUNT(*), COUNT(*) FILTER (WHERE ttl > 0) "
            "FROM packet_evidence "
            "WHERE probe_id = :pid "
            "AND timestamp > NOW() - :window * INTERVAL '1 second'"
        ),
        {"pid": probe_id, "window": window_s},
    )
    total, successes = result.fetchone()
    if total == 0:
        return 0.0, 0.0, False
    pct_loss = ((total - successes) / total) * 100
    pct_avail = (successes / total) * 100
    return pct_loss, pct_avail, True


async def _push_probe_metrics() -> None:
    if manager.count == 0:
        return

    keys = await redis.keys("metrics:latest:probe:*")
    for key in keys:
        raw = await redis.get(key)
        if raw is None:
            continue
        m = json.loads(raw)
        await manager.broadcast(json.dumps({
            "type": "probe_metric_update",
            "probe_id": m["probe_id"],
            "link_id": m["link_id"],
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
            "probe_id": pe["probe_id"],
            "link_id": pe["link_id"],
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


async def _evaluate_probe_alerts() -> None:
    async with engine.begin() as conn:
        result = await conn.execute(text("SELECT id FROM probes"))
        probe_ids = [row[0] for row in result.fetchall()]
    for probe_id in probe_ids:
        await evaluate_probe(probe_id)


async def _check_heartbeats_job() -> None:
    await check_heartbeats()


async def _check_probe_heartbeats_job() -> None:
    await check_probe_heartbeats()


async def _reload_rules_startup() -> None:
    await reload_rules()


def start_scheduler() -> None:
    global _started
    if not _started:
        scheduler.add_job(_reload_rules_startup, id="reload_rules_startup")
        scheduler.add_job(_collect_all_nodes, "interval", seconds=5, id="collect_metrics")
        scheduler.add_job(_collect_probes, "interval", seconds=5, id="collect_probes")
        scheduler.add_job(_push_metrics, "interval", seconds=1, id="push_metrics")
        scheduler.add_job(_push_probe_metrics, "interval", seconds=1, id="push_probe_metrics")
        scheduler.add_job(_evaluate_alerts, "interval", seconds=5, id="evaluate_alerts")
        scheduler.add_job(_evaluate_probe_alerts, "interval", seconds=5, id="evaluate_probe_alerts")
        scheduler.add_job(_check_heartbeats_job, "interval", seconds=15, id="check_heartbeats")
        scheduler.add_job(
            _check_probe_heartbeats_job, "interval", seconds=15, id="check_probe_heartbeats"
        )
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
