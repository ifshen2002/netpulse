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


def clear_cooldown(node_id: str, alert_type: str) -> None:
    """Clear cooldown for a specific node+alert_type (called on chaos injection)."""
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
                "incident_id": incident_id,
                "node_id": node_id,
                "alert_type": alert_type,
                "message": message,
                "timestamp": now.isoformat(),
            }
        )
    )
    return alert_id, incident_id


# ── standalone alert (chaos alert-only types) ─────────────────────

async def fire_standalone_alert(
    node_id: str, alert_type: str, message: str
) -> str:
    alert_id = await _insert_alert(node_id, None, alert_type, message)
    now = _utcnow()
    await manager.broadcast(
        _event(
            {
                "type": "alert_fired",
                "alert_id": alert_id,
                "incident_id": None,
                "node_id": node_id,
                "alert_type": alert_type,
                "message": message,
                "timestamp": now.isoformat(),
            }
        )
    )
    return alert_id


# ── recovery ──────────────────────────────────────────────────────

async def _handle_recovery(node_id: str) -> None:
    from services.chaos import active_for_node

    # Never auto-resolve while chaos overlay is active — the operator
    # deliberately injected it and expects the incident to persist.
    if active_for_node(node_id):
        _clean_streaks.pop(node_id, None)
        return

    if node_id not in _open_incidents:
        _clean_streaks.pop(node_id, None)
        return

    _clean_streaks[node_id] = _clean_streaks.get(node_id, 0) + 1
    if _clean_streaks[node_id] >= RECOVERY_STREAK:
        await _resolve_incident(node_id)


async def resolve_for_node(node_id: str, now: datetime | None = None) -> None:
    """Resolve any open incident for a node immediately (called on chaos recover)."""
    incident_id = _open_incidents.pop(node_id, None)
    _clear_cooldowns(node_id)
    _clean_streaks.pop(node_id, None)

    if incident_id is None:
        return

    now = now or _utcnow()
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


# ── V2 probe alerting ─────────────────────────────────────────────
# Separate in-memory state from V1 to prevent key collisions.

# Hardcoded threshold defaults — used if no alert_rules are loaded.
_probe_latency_threshold_ms = 300
_probe_packet_loss_threshold_pct = 5.0
_probe_availability_threshold_pct = 95.0

# Rule cache — loaded from DB, refreshed on rule CRUD.
_active_rules: list[dict] = []
_rules_loaded = False


def get_probe_thresholds() -> dict:
    """Return current probe alert thresholds (legacy flat format)."""
    return {
        "latency_ms": _probe_latency_threshold_ms,
        "packet_loss_pct": _probe_packet_loss_threshold_pct,
        "availability_pct": _probe_availability_threshold_pct,
    }


def set_probe_threshold(
    latency_ms: int | None = None,
    packet_loss_pct: float | None = None,
    availability_pct: float | None = None,
) -> None:
    """Update legacy probe alert thresholds at runtime."""
    global _probe_latency_threshold_ms
    global _probe_packet_loss_threshold_pct
    global _probe_availability_threshold_pct
    if latency_ms is not None:
        _probe_latency_threshold_ms = latency_ms
    if packet_loss_pct is not None:
        _probe_packet_loss_threshold_pct = packet_loss_pct
    if availability_pct is not None:
        _probe_availability_threshold_pct = availability_pct


async def reload_rules() -> None:
    """Reload alert rules from DB into memory cache."""
    global _active_rules, _rules_loaded
    try:
        async with engine.begin() as conn:
            rows = (await conn.execute(
                text(
                    "SELECT id, name, metric, operator, threshold, severity "
                    "FROM alert_rules WHERE enabled = true ORDER BY severity, name"
                )
            )).fetchall()
        _active_rules = [
            {
                "id": r[0],
                "name": r[1],
                "metric": r[2],
                "operator": r[3],
                "threshold": float(r[4]),
                "severity": r[5],
                "alert_type": r[0].replace("-", "_"),
            }
            for r in rows
        ]
        _rules_loaded = True
    except Exception:
        # Table may not exist yet (before migration runs)
        _active_rules = []
        _rules_loaded = False


def _evaluate_condition(value: float, operator: str, threshold: float) -> bool:
    if operator == ">":
        return value > threshold
    elif operator == "<":
        return value < threshold
    elif operator == ">=":
        return value >= threshold
    elif operator == "<=":
        return value <= threshold
    return False


_probe_cooldowns: dict[tuple[str, str], datetime] = {}
_probe_clean_streaks: dict[str, int] = {}
_probe_open_incidents: dict[str, str] = {}
_probe_heartbeats: dict[str, datetime] = {}

# ── V2 rule-state tracking (state-based alerting) ────────────────
# Maps (probe_id, rule_id) → alert_id when a rule condition is currently active.
# Removed when the condition drops back within threshold.
_active_rule_state: dict[tuple[str, str], str] = {}


def _probe_is_in_cooldown(probe_id: str, alert_type: str) -> bool:
    last = _probe_cooldowns.get((probe_id, alert_type))
    if last is None:
        return False
    return (_utcnow() - last).total_seconds() < COOLDOWN_S


def _probe_set_cooldown(probe_id: str, alert_type: str) -> None:
    _probe_cooldowns[(probe_id, alert_type)] = _utcnow()


async def _insert_probe_alert(
    probe_id: str, incident_id: str | None, alert_type: str, message: str
) -> str:
    alert_id = str(uuid.uuid4())
    now = _utcnow()
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO alerts (id, probe_id, incident_id, alert_type, "
                "message, fired_at) "
                "VALUES (:id, :probe_id, :incident_id, :alert_type, :message, :fired_at)"
            ),
            {
                "id": alert_id,
                "probe_id": probe_id,
                "incident_id": incident_id,
                "alert_type": alert_type,
                "message": message,
                "fired_at": now,
            },
        )
    return alert_id


async def _create_probe_incident(probe_id: str, alert_type: str) -> str:
    existing = _probe_open_incidents.get(probe_id)
    if existing is not None:
        return existing

    incident_id = str(uuid.uuid4())
    title = f"{probe_id} {alert_type}"
    now = _utcnow()
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO incidents (id, title, status, probe_id, opened_at) "
                "VALUES (:id, :title, 'open', :probe_id, :opened_at)"
            ),
            {
                "id": incident_id,
                "title": title,
                "probe_id": probe_id,
                "opened_at": now,
            },
        )

    _probe_open_incidents[probe_id] = incident_id
    await manager.broadcast(
        _event(
            {
                "type": "incident_opened",
                "incident_id": incident_id,
                "title": title,
                "probe_id": probe_id,
                "timestamp": now.isoformat(),
            }
        )
    )
    return incident_id


async def _resolve_probe_incident(probe_id: str) -> None:
    incident_id = _probe_open_incidents.pop(probe_id, None)
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

    # Clear all in-memory state for this probe
    for key in list(_probe_cooldowns.keys()):
        if key[0] == probe_id:
            del _probe_cooldowns[key]
    for key in list(_active_rule_state.keys()):
        if key[0] == probe_id:
            del _active_rule_state[key]
    _probe_clean_streaks.pop(probe_id, None)

    await manager.broadcast(
        _event(
            {
                "type": "incident_closed",
                "incident_id": incident_id,
                "probe_id": probe_id,
                "timestamp": now.isoformat(),
            }
        )
    )


async def _fire_probe_alert(
    probe_id: str, alert_type: str, message: str, evidence_id: str | None = None
) -> tuple[str, str] | tuple[None, None]:
    if _probe_is_in_cooldown(probe_id, alert_type):
        return None, None

    _probe_set_cooldown(probe_id, alert_type)
    incident_id = await _create_probe_incident(probe_id, alert_type)
    alert_id = await _insert_probe_alert(probe_id, incident_id, alert_type, message)
    now = _utcnow()

    await manager.broadcast(
        _event(
            {
                "type": "alert_fired",
                "alert_id": alert_id,
                "incident_id": incident_id,
                "probe_id": probe_id,
                "alert_type": alert_type,
                "message": message,
                "evidence_id": evidence_id,
                "timestamp": now.isoformat(),
            }
        )
    )
    return alert_id, incident_id


async def _handle_probe_recovery(probe_id: str) -> None:
    if probe_id not in _probe_open_incidents:
        _probe_clean_streaks.pop(probe_id, None)
        return

    _probe_clean_streaks[probe_id] = _probe_clean_streaks.get(probe_id, 0) + 1
    if _probe_clean_streaks[probe_id] >= RECOVERY_STREAK:
        await _resolve_probe_incident(probe_id)


async def evaluate_probe(probe_id: str) -> list[dict]:
    """Evaluate probe telemetry against alert rules (or legacy thresholds)."""
    raw = await redis.get(f"metrics:latest:probe:{probe_id}")
    if raw is None:
        return []

    m = json.loads(raw)
    _probe_heartbeats[probe_id] = _utcnow()

    # Do not alert while status is gray — no data yet
    if m.get("status") == "gray":
        return []

    evidence_id = m.get("packet_evidence_id")

    if _rules_loaded and _active_rules:
        return await _evaluate_rules(probe_id, m, evidence_id)

    # Legacy fallback — used when alert_rules table doesn't exist
    latency = m.get("latency_ms", 0)
    loss = m.get("packet_loss_pct", 0)
    avail = m.get("availability_pct", 0)

    fired = []

    if latency > _probe_latency_threshold_ms:
        aid, _ = await _fire_probe_alert(
            probe_id, "probe_latency_high",
            f"Latency {latency:.1f}ms > {_probe_latency_threshold_ms}ms [evidence {evidence_id}]",
            evidence_id,
        )
        if aid:
            fired.append({"alert_id": aid, "alert_type": "probe_latency_high"})

    t_loss = _probe_packet_loss_threshold_pct
    if loss >= t_loss:
        aid, _ = await _fire_probe_alert(
            probe_id, "probe_packet_loss_high",
            f"Packet loss {loss:.1f}% >= {t_loss}% [evidence {evidence_id}]",
            evidence_id,
        )
        if aid:
            fired.append({"alert_id": aid, "alert_type": "probe_packet_loss_high"})

    t_avail = _probe_availability_threshold_pct
    if avail <= t_avail:
        aid, _ = await _fire_probe_alert(
            probe_id, "probe_availability_low",
            f"Availability {avail:.1f}% <= {t_avail}% [evidence {evidence_id}]",
            evidence_id,
        )
        if aid:
            fired.append({"alert_id": aid, "alert_type": "probe_availability_low"})

    if fired:
        _probe_clean_streaks[probe_id] = 0
    else:
        await _handle_probe_recovery(probe_id)

    return fired


async def _evaluate_rules(probe_id: str, m: dict, evidence_id: str | None) -> list[dict]:
    """Evaluate all active rules against probe telemetry with state-based semantics.

    State-based alerting:
      - Condition becomes true + not already active → fire alert, mark active
      - Condition stays true + already active → no-op (condition persists)
      - Condition becomes false + was active → resolve alert for this rule
      - Incident closes only when ALL rules for the probe are resolved.
    """
    metric_values = {
        "latency": m.get("latency_ms", 0),
        "packet_loss": m.get("packet_loss_pct", 0),
        "availability": m.get("availability_pct", 0),
    }

    fired = []
    newly_resolved = []

    for rule in _active_rules:
        rid = rule["id"]
        alert_type = rule["alert_type"]
        state_key = (probe_id, rid)
        value = metric_values.get(rule["metric"])
        if value is None:
            continue

        condition_true = _evaluate_condition(value, rule["operator"], rule["threshold"])

        if condition_true:
            if state_key in _active_rule_state:
                # Condition persists — alert stays open, nothing to do.
                continue
            # Condition newly tripped — fire alert (cooldown still guards against storms).
            message = (
                f"[{rule['severity'].upper()}] {rule['name']}: "
                f"{rule['metric']} {rule['operator']} {rule['threshold']} "
                f"(observed: {value:.1f}) [evidence {evidence_id}]"
            )
            aid, _ = await _fire_probe_alert(probe_id, alert_type, message, evidence_id)
            if aid:
                _active_rule_state[state_key] = aid
                fired.append({"alert_id": aid, "alert_type": alert_type, "rule_id": rid})
        else:
            if state_key in _active_rule_state:
                # Condition resolved — mark rule inactive, resolve the alert row.
                alert_id = _active_rule_state.pop(state_key)
                newly_resolved.append(alert_id)
                await _resolve_alert_row(alert_id)

    # Resolve incident only when ALL previously-active rules have resolved
    # AND no rules are currently active for this probe.
    active_for_probe = any(
        state_key[0] == probe_id for state_key in _active_rule_state
    )

    if fired:
        _probe_clean_streaks[probe_id] = 0
    elif not active_for_probe:
        await _handle_probe_recovery(probe_id)

    return fired


async def _resolve_alert_row(alert_id: str) -> None:
    """Set resolved_at on a single alert row."""
    now = _utcnow()
    async with engine.begin() as conn:
        await conn.execute(
            text("UPDATE alerts SET resolved_at = :now WHERE id = :id AND resolved_at IS NULL"),
            {"now": now, "id": alert_id},
        )


async def check_probe_heartbeats() -> None:
    now = _utcnow()
    async with engine.begin() as conn:
        result = await conn.execute(text("SELECT id FROM probes"))
        probe_ids = [row[0] for row in result.fetchall()]

    for probe_id in probe_ids:
        last = _probe_heartbeats.get(probe_id)
        if last is None:
            continue
        if (now - last).total_seconds() > HEARTBEAT_TIMEOUT_S:
            await _fire_probe_alert(
                probe_id,
                "probe_heartbeat_timeout",
                f"No heartbeat for {HEARTBEAT_TIMEOUT_S}s",
            )
