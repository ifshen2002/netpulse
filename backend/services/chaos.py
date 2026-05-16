import json
import random
import uuid
from datetime import datetime, timezone

from sqlalchemy import text

from db import engine
from routers.websocket import manager

# ── in-memory chaos registry ────────────────────────────────────────
_active: dict[str, list[str]] = {}       # node_id → [chaos_type, ...]
_loss_counter: dict[str, int] = {}        # node_id → call count

# All chaos types from ARCHITECTURE.md Section 10
OVERLAY_TYPES = {"latency_spike", "cpu_spike", "packet_loss"}
ALERT_ONLY_TYPES = {"db_exhaustion", "cache_unavailable"}
ALL_TYPES = OVERLAY_TYPES | ALERT_ONLY_TYPES


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ── overlay engine ──────────────────────────────────────────────────

def apply_overlay(metrics: dict) -> dict | None:
    node_id = metrics.get("node_id", "")

    # Node-1 is read-only — never mutated
    if node_id == "node-1":
        return metrics

    active = _active.get(node_id, [])
    if not active:
        return metrics

    # Copy before mutating — raw metrics are never modified in-place
    m = dict(metrics)

    for chaos_type in active:
        if chaos_type == "latency_spike":
            m["latency_ms"] = m.get("latency_ms", 0) + random.uniform(200, 800)
        elif chaos_type == "cpu_spike":
            config = _get_config(node_id, chaos_type)
            bonus = float(config.get("value", 30)) if config else 30.0
            m["cpu"] = min(100.0, m.get("cpu", 0) + bonus)
        elif chaos_type == "packet_loss":
            _loss_counter[node_id] = _loss_counter.get(node_id, 0) + 1
            if _loss_counter[node_id] % 5 == 0:
                return None

    _recompute_status(m)
    return m


def _recompute_status(m: dict) -> None:
    cpu = m.get("cpu", 0)
    memory = m.get("memory", 0)
    latency_ms = m.get("latency_ms", 0)
    if cpu > 90 or memory > 95 or latency_ms > 1000:
        m["status"] = "red"
    elif cpu > 80 or memory > 90 or latency_ms > 500:
        m["status"] = "yellow"
    else:
        m["status"] = "green"


# ── chaos lifecycle ─────────────────────────────────────────────────

async def inject(
    node_id: str, chaos_type: str, config: dict | None = None
) -> str:
    if chaos_type not in ALL_TYPES:
        raise ValueError(f"Unknown chaos type: {chaos_type}")

    event_id = str(uuid.uuid4())
    now = _utcnow()

    async with engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO chaos_events (id, chaos_type, node_id, "
                "started_at, config) "
                "VALUES (:id, :chaos_type, :node_id, :started_at, :config)"
            ),
            {
                "id": event_id,
                "chaos_type": chaos_type,
                "node_id": node_id,
                "started_at": now,
                "config": json.dumps(config) if config else None,
            },
        )

    # Alert-only types are one-shot — don't persist in overlay registry
    if chaos_type in OVERLAY_TYPES:
        _active.setdefault(node_id, []).append(chaos_type)
        if config:
            _config_cache[f"{node_id}:{chaos_type}"] = config
        await manager.broadcast(
            json.dumps(
                {
                    "type": "node_status_changed",
                    "node_id": node_id,
                    "status": "yellow",
                    "timestamp": now.isoformat(),
                }
            )
        )

    return event_id


async def recover_all(node_id: str | None = None) -> int:
    now = _utcnow()
    removed = 0

    nodes = [node_id] if node_id else list(_active.keys())
    for nid in nodes:
        types = _active.pop(nid, [])
        for ct in types:
            _config_cache.pop(f"{nid}:{ct}", None)
        removed += len(types)
        _loss_counter.pop(nid, None)

    if removed == 0:
        return 0

    async with engine.begin() as conn:
        if node_id:
            await conn.execute(
                text(
                    "UPDATE chaos_events SET ended_at = :now "
                    "WHERE node_id = :node_id AND ended_at IS NULL"
                ),
                {"now": now, "node_id": node_id},
            )
        else:
            await conn.execute(
                text(
                    "UPDATE chaos_events SET ended_at = :now "
                    "WHERE ended_at IS NULL"
                ),
                {"now": now},
            )

    for nid in nodes:
        await manager.broadcast(
            json.dumps(
                {
                    "type": "node_status_changed",
                    "node_id": nid,
                    "status": "green",
                    "timestamp": now.isoformat(),
                }
            )
        )

    return removed


def status() -> dict:
    return {"active": dict(_active), "loss_counter": dict(_loss_counter)}


# ── config helpers ──────────────────────────────────────────────────

_config_cache: dict[str, dict] = {}  # event_id → config


def _get_config(node_id: str, chaos_type: str) -> dict | None:
    return _config_cache.get(f"{node_id}:{chaos_type}")
