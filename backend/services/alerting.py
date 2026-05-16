import json
import uuid
from datetime import datetime, timezone

from sqlalchemy import text

from db import engine
from redis_client import client as redis
from routers.websocket import manager

# ── in-memory state ──────────────────────────────────────────────
_cooldowns: dict[tuple[str, str], datetime] = {}
_clean_streaks: dict[str, int] = {}
_open_incidents: dict[str, str] = {}
_heartbeats: dict[str, datetime] = {}

HEARTBEAT_TIMEOUT_S = 15
COOLDOWN_S = 60
RECOVERY_STREAK = 3


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ── cooldown helpers ──────────────────────────────────────────────

def _is_in_cooldown(node_id: str, alert_type: str) -> bool:
    key = (node_id, alert_type)
    last = _cooldowns.get(key)
    if last is None:
        return False
    return (_utcnow() - last).total_seconds() < COOLDOWN_S


def _set_cooldown(node_id: str, alert_type: str) -> None:
    _cooldowns[(node_id, alert_type)] = _utcnow()


def _clear_cooldowns(node_id: str) -> None:
    for alert_type in ("cpu_high", "latency_spike", "heartbeat_timeout"):
        _cooldowns.pop((node_id, alert_type), None)


# ── broadcast helper ──────────────────────────────────────────────

def _event(event_dict: dict) -> str:
    return json.dumps(event_dict)


# ── alert persistence ─────────────────────────────────────────────

async def _insert_alert(
    node_id: str, incident_id: str | None, alert_type: str, message: str
) -> str:
    alert_id = str(uuid.uuid4())
    now = _utcnow()
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO alerts (id, node_id, incident_id, alert_type, "
                "message, fired_at) "
                "VALUES (:id, :node_id, :incident_id, :alert_type, :message, :fired_at)"
            ),
            {
                "id": alert_id,
                "node_id": node_id,
                "incident_id": incident_id,
                "alert_type": alert_type,
                "message": message,
                "fired_at": now,
            },
        )
    return alert_id


# ── incident persistence ──────────────────────────────────────────

async def _create_incident(node_id: str, alert_type: str) -> str:
    existing = _open_incidents.get(node_id)
    if existing is not None:
        return existing

    incident_id = str(uuid.uuid4())
    title = f"{node_id} {alert_type} incident"
    now = _utcnow()
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO incidents (id, title, status, opened_at) "
                "VALUES (:id, :title, 'open', :opened_at)"
            ),
            {"id": incident_id, "title": title, "opened_at": now},
        )

    _open_incidents[node_id] = incident_id
    await manager.broadcast(
        _event(
            {
                "type": "incident_opened",
                "incident_id": incident_id,
                "title": title,
                "node_id": node_id,
                "timestamp": now.isoformat(),
            }
        )
    )
    return incident_id


async def _resolve_incident(node_id: str) -> None:
    incident_id = _open_incidents.pop(node_id, None)
    if incident_id is None:
        return

    now = _utcnow()
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "UPDATE incidents SET status = 'closed', closed_at = :now "
                "WHERE id = :id"
            ),
            {"now": now, "id": incident_id},
        )
        await conn.execute(
            text(
                "UPDATE alerts SET resolved_at = :now "
                "WHERE incident_id = :id AND resolved_at IS NULL"
            ),
            {"now": now, "id": incident_id},
        )

    _clear_cooldowns(node_id)
    _clean_streaks.pop(node_id, None)

    await manager.broadcast(
        _event(
            {
                "type": "incident_closed",
                "incident_id": incident_id,
                "node_id": node_id,
                "timestamp": now.isoformat(),
            }
        )
    )


# ── alert firing ──────────────────────────────────────────────────

async def _fire_alert(
    node_id: str, alert_type: str, message: str
) -> tuple[str, str] | tuple[None, None]:
    if _is_in_cooldown(node_id, alert_type):
        return None, None

    _set_cooldown(node_id, alert_type)
    incident_id = await _create_incident(node_id, alert_type)
    alert_id = await _insert_alert(node_id, incident_id, alert_type, message)
    now = _utcnow()

    await manager.broadcast(
        _event(
            {
                "type": "alert_fired",
                "alert_id": alert_id,
                "node_id": node_id,
                "alert_type": alert_type,
                "message": message,
                "timestamp": now.isoformat(),
            }
        )
    )
    return alert_id, incident_id


# ── recovery ──────────────────────────────────────────────────────

async def _handle_recovery(node_id: str) -> None:
    if node_id not in _open_incidents:
        _clean_streaks.pop(node_id, None)
        return

    _clean_streaks[node_id] = _clean_streaks.get(node_id, 0) + 1
    if _clean_streaks[node_id] >= RECOVERY_STREAK:
        await _resolve_incident(node_id)


# ── public API ────────────────────────────────────────────────────

async def evaluate(node_id: str) -> list[dict]:
    raw = await redis.get(f"metrics:latest:{node_id}")
    if raw is None:
        return []

    m = json.loads(raw)
    _heartbeats[node_id] = _utcnow()

    cpu = m.get("cpu", 0)
    latency = m.get("latency_ms", 0)

    fired = []

    if cpu > 80:
        aid, _ = await _fire_alert(node_id, "cpu_high", f"CPU at {cpu:.0f}%")
        if aid:
            fired.append({"alert_id": aid, "alert_type": "cpu_high"})

    if latency > 500:
        aid, _ = await _fire_alert(
            node_id, "latency_spike", f"Latency at {latency:.0f}ms"
        )
        if aid:
            fired.append({"alert_id": aid, "alert_type": "latency_spike"})

    if fired:
        _clean_streaks[node_id] = 0
    else:
        await _handle_recovery(node_id)

    return fired


async def check_heartbeats() -> None:
    now = _utcnow()
    for node_id in ("node-1", "node-2", "node-3"):
        last = _heartbeats.get(node_id)
        if last is None:
            continue
        if (now - last).total_seconds() > HEARTBEAT_TIMEOUT_S:
            await _fire_alert(
                node_id,
                "heartbeat_timeout",
                f"No heartbeat for {HEARTBEAT_TIMEOUT_S}s",
            )
