import json
import random
import uuid
from datetime import datetime, timezone

from sqlalchemy import text

from db import engine
from routers.websocket import manager

# ── in-memory chaos registry ────────────────────────────────────────
_active: dict[str, dict[str, str]] = {}   # node_id → {chaos_type: intensity}
_loss_counter: dict[str, int] = {}         # node_id → call count
_effect_values: dict[tuple[str, str], float] = {}  # (node_id, chaos_type) → value

OVERLAY_TYPES = {"latency_spike", "cpu_spike", "packet_loss"}
ALERT_ONLY_TYPES = {"db_exhaustion", "cache_unavailable"}
ALL_TYPES = OVERLAY_TYPES | ALERT_ONLY_TYPES
INTENSITIES = {"low", "medium", "high", "critical"}

# ── intensity → realistic range ─────────────────────────────────────
# Values are randomly picked once per injection and stored in _effect_values.
# This simulates real-world variance: a "high CPU" incident might be 75% or 95%.

_CPU_RANGES = {
    "low": (5, 15), "medium": (30, 50), "high": (80, 95), "critical": (95, 100),
}
_LATENCY_RANGES = {
    "low": (50, 150), "medium": (200, 400), "high": (500, 800), "critical": (800, 1500),
}
_LOSS_RANGES = {"low": (10, 20), "medium": (5, 10), "high": (2, 5), "critical": (1, 2)}

DEFAULT_INTENSITY = "high"


def _random_in_range(intensity: str, ranges: dict) -> float:
    lo, hi = ranges[intensity]
    return random.uniform(lo, hi)


def _get_effect(node_id: str, chaos_type: str) -> float | None:
    return _effect_values.get((node_id, chaos_type))


def _set_effect(node_id: str, chaos_type: str, value: float) -> None:
    _effect_values[(node_id, chaos_type)] = value


def _clear_effect(node_id: str, chaos_type: str) -> None:
    _effect_values.pop((node_id, chaos_type), None)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ── overlay engine ──────────────────────────────────────────────────

def apply_overlay(metrics: dict) -> dict | None:
    node_id = metrics.get("node_id", "")

    # Node-1 is read-only — never mutated
    if node_id == "node-1":
        return metrics

    active = _active.get(node_id, {})
    if not active:
        return metrics

    m = dict(metrics)

    for chaos_type, _intensity in active.items():
        if chaos_type == "latency_spike":
            val = _get_effect(node_id, chaos_type)
            m["latency_ms"] = m.get("latency_ms", 0) + (val or 600)
        elif chaos_type == "cpu_spike":
            target = _get_effect(node_id, chaos_type)
            m["cpu"] = max(m.get("cpu", 0), target or 90)
        elif chaos_type == "packet_loss":
            val = _get_effect(node_id, chaos_type)
            _loss_counter[node_id] = _loss_counter.get(node_id, 0) + 1
            n = int(val) if val else 4
            if _loss_counter[node_id] % n == 0:
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

    intensity = (config or {}).get("intensity", DEFAULT_INTENSITY)
    if chaos_type in OVERLAY_TYPES and intensity not in INTENSITIES:
        raise ValueError(f"Unknown intensity: {intensity}")

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

    if chaos_type in OVERLAY_TYPES:
        _active.setdefault(node_id, {})[chaos_type] = intensity
        # Generate a realistic random value within the intensity range and store it.
        # This simulates real operational variance: a "high CPU" incident could
        # spike anywhere from 75-95%, not a fixed 92%.
        if chaos_type == "cpu_spike":
            _set_effect(node_id, chaos_type, _random_in_range(intensity, _CPU_RANGES))
        elif chaos_type == "latency_spike":
            _set_effect(node_id, chaos_type, _random_in_range(intensity, _LATENCY_RANGES))
        elif chaos_type == "packet_loss":
            _set_effect(node_id, chaos_type, _random_in_range(intensity, _LOSS_RANGES))
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


async def recover_all(node_id: str | None = None, chaos_type: str | None = None) -> int:
    from services import alerting as alerting_svc

    now = _utcnow()
    removed = 0

    nodes = [node_id] if node_id else list(_active.keys())
    for nid in nodes:
        if chaos_type:
            popped = _active.get(nid, {}).pop(chaos_type, None)
            if popped:
                removed += 1
                _clear_effect(nid, chaos_type)
                if not _active.get(nid):  # no more active chaos for this node
                    _active.pop(nid, None)
                    _loss_counter.pop(nid, None)
        else:
            types = _active.pop(nid, {})
            removed += len(types)
            for ct in types:
                _clear_effect(nid, ct)
            _loss_counter.pop(nid, None)

    if removed == 0:
        return 0

    async with engine.begin() as conn:
        if chaos_type and node_id:
            await conn.execute(
                text(
                    "UPDATE chaos_events SET ended_at = :now "
                    "WHERE node_id = :node_id AND chaos_type = :chaos_type AND ended_at IS NULL"
                ),
                {"now": now, "node_id": node_id, "chaos_type": chaos_type},
            )
        elif node_id:
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
        still_active = _active.get(nid, {})
        if not still_active:
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
            # Resolve any open incident for fully recovered nodes
            await alerting_svc.resolve_for_node(nid, now)

    return removed


def status() -> dict:
    return {
        "active": dict(_active),
        "loss_counter": dict(_loss_counter),
        "effect_values": {f"{k[0]}:{k[1]}": v for k, v in _effect_values.items()},
    }


def active_for_node(node_id: str) -> bool:
    """Returns True if any overlay chaos is active for the node."""
    return node_id in _active and len(_active[node_id]) > 0
