import json
import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import text

from db import engine
import redis_client
from routers.websocket import manager

logger = logging.getLogger(__name__)

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
    node_id: str, incident_id: str | None, alert_type: str, message: str,
    project_id: str | None = None,
) -> str:
    alert_id = str(uuid.uuid4())
    now = _utcnow()
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO alerts (id, node_id, incident_id, alert_type, "
                "message, project_id, fired_at) "
                "VALUES (:id, :node_id, :incident_id, :alert_type, :message, :project_id, :fired_at)"
            ),
            {
                "id": alert_id,
                "node_id": node_id,
                "incident_id": incident_id,
                "alert_type": alert_type,
                "message": message,
                "project_id": project_id,
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

    # Auto-resolve notifications for this incident
    await _resolve_notifications_for_incident(incident_id)


# ── alert firing ──────────────────────────────────────────────────

async def _fire_alert(
    node_id: str, alert_type: str, message: str
) -> tuple[str, str] | tuple[None, None]:
    if _is_in_cooldown(node_id, alert_type):
        return None, None

    _set_cooldown(node_id, alert_type)
    incident_id = await _create_incident(node_id, alert_type)

    # Look up project_id for the node
    project_id = None
    async with engine.begin() as conn:
        row = (await conn.execute(
            text("SELECT project_id FROM nodes WHERE id = :id"),
            {"id": node_id},
        )).fetchone()
        if row:
            project_id = row[0]

    alert_id = await _insert_alert(node_id, incident_id, alert_type, message, project_id)
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

    # Deliver in-app notifications to matching subscribers
    await _deliver_notifications_for_node(
        node_id, alert_id, incident_id, alert_type, message, project_id,
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

    # Auto-resolve notifications for this incident
    await _resolve_notifications_for_incident(incident_id)


# ── public API ────────────────────────────────────────────────────

async def evaluate(node_id: str) -> list[dict]:
    raw = await redis_client.client.get(f"metrics:latest:{node_id}")
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


# ── V2 endpoint alerting ───────────────────────────────────────────
# Single source of truth: alert_rules table. No legacy fallback thresholds.

# Rule cache — loaded from DB, refreshed on rule CRUD.
_active_rules: list[dict] = []
_rules_loaded = False


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


_endpoint_cooldowns: dict[tuple[str, str], datetime] = {}
_endpoint_clean_streaks: dict[str, int] = {}
_endpoint_open_incidents: dict[str, str] = {}
_endpoint_heartbeats: dict[str, datetime] = {}

# ── V2 rule-state tracking (state-based alerting) ────────────────
# Maps (endpoint_id, rule_id) → alert_id when a rule condition is currently active.
# Removed when the condition drops back within threshold.
_active_rule_state: dict[tuple[str, str], str] = {}


def _endpoint_is_in_cooldown(endpoint_id: str, alert_type: str) -> bool:
    last = _endpoint_cooldowns.get((endpoint_id, alert_type))
    if last is None:
        return False
    return (_utcnow() - last).total_seconds() < COOLDOWN_S


def _endpoint_set_cooldown(endpoint_id: str, alert_type: str) -> None:
    _endpoint_cooldowns[(endpoint_id, alert_type)] = _utcnow()


async def _insert_endpoint_alert(
    endpoint_id: str, incident_id: str | None, alert_type: str, message: str,
    project_id: str | None = None,
) -> str:
    alert_id = str(uuid.uuid4())
    now = _utcnow()
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO alerts (id, endpoint_id, incident_id, alert_type, "
                "message, project_id, fired_at) "
                "VALUES (:id, :endpoint_id, :incident_id, :alert_type, :message, :project_id, :fired_at)"
            ),
            {
                "id": alert_id,
                "endpoint_id": endpoint_id,
                "incident_id": incident_id,
                "alert_type": alert_type,
                "message": message,
                "project_id": project_id,
                "fired_at": now,
            },
        )
    return alert_id


async def _create_endpoint_incident(endpoint_id: str, alert_type: str) -> str:
    existing = _endpoint_open_incidents.get(endpoint_id)
    if existing is not None:
        return existing

    incident_id = str(uuid.uuid4())
    title = f"{endpoint_id} {alert_type}"
    now = _utcnow()

    # Look up project_id for broadcast scoping
    ep_project_id = None
    async with engine.connect() as conn:
        row = (await conn.execute(
            text("SELECT project_id FROM endpoints WHERE id = :id"),
            {"id": endpoint_id},
        )).fetchone()
        if row:
            ep_project_id = row[0]

    async with engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO incidents (id, title, status, endpoint_id, opened_at) "
                "VALUES (:id, :title, 'open', :endpoint_id, :opened_at)"
            ),
            {
                "id": incident_id,
                "title": title,
                "endpoint_id": endpoint_id,
                "opened_at": now,
            },
        )

    _endpoint_open_incidents[endpoint_id] = incident_id
    await manager.broadcast(
        _event(
            {
                "type": "incident_opened",
                "incident_id": incident_id,
                "title": title,
                "endpoint_id": endpoint_id,
                "timestamp": now.isoformat(),
            }
        ),
        project_id=ep_project_id,
    )
    return incident_id


async def _resolve_endpoint_incident(endpoint_id: str) -> None:
    incident_id = _endpoint_open_incidents.pop(endpoint_id, None)
    if incident_id is None:
        return

    now = _utcnow()

    # Look up project_id for broadcast scoping
    ep_project_id = None
    async with engine.connect() as conn:
        row = (await conn.execute(
            text("SELECT project_id FROM endpoints WHERE id = :id"),
            {"id": endpoint_id},
        )).fetchone()
        if row:
            ep_project_id = row[0]

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

    # Clear all in-memory state for this endpoint
    for key in list(_endpoint_cooldowns.keys()):
        if key[0] == endpoint_id:
            del _endpoint_cooldowns[key]
    for key in list(_active_rule_state.keys()):
        if key[0] == endpoint_id:
            del _active_rule_state[key]
    _endpoint_clean_streaks.pop(endpoint_id, None)

    await manager.broadcast(
        _event(
            {
                "type": "incident_closed",
                "incident_id": incident_id,
                "endpoint_id": endpoint_id,
                "timestamp": now.isoformat(),
            }
        ),
        project_id=ep_project_id,
    )

    # Auto-resolve notifications for this incident
    await _resolve_notifications_for_incident(incident_id)


async def _fire_endpoint_alert(
    endpoint_id: str, alert_type: str, message: str, evidence_id: str | None = None
) -> tuple[str, str] | tuple[None, None]:
    if _endpoint_is_in_cooldown(endpoint_id, alert_type):
        return None, None

    _endpoint_set_cooldown(endpoint_id, alert_type)
    incident_id = await _create_endpoint_incident(endpoint_id, alert_type)

    # Look up project_id for the endpoint
    project_id = None
    async with engine.begin() as conn:
        row = (await conn.execute(
            text("SELECT project_id FROM endpoints WHERE id = :id"),
            {"id": endpoint_id},
        )).fetchone()
        if row:
            project_id = row[0]

    alert_id = await _insert_endpoint_alert(
        endpoint_id, incident_id, alert_type, message, project_id,
    )
    now = _utcnow()

    await manager.broadcast(
        _event(
            {
                "type": "alert_fired",
                "alert_id": alert_id,
                "incident_id": incident_id,
                "endpoint_id": endpoint_id,
                "alert_type": alert_type,
                "message": message,
                "evidence_id": evidence_id,
                "timestamp": now.isoformat(),
            }
        ),
        project_id=project_id,
    )

    # Deliver in-app notifications to matching subscribers
    await _deliver_notifications_for_endpoint(
        endpoint_id, alert_id, incident_id, alert_type, message, project_id,
    )

    return alert_id, incident_id


async def _handle_endpoint_recovery(endpoint_id: str) -> None:
    if endpoint_id not in _endpoint_open_incidents:
        _endpoint_clean_streaks.pop(endpoint_id, None)
        return

    _endpoint_clean_streaks[endpoint_id] = _endpoint_clean_streaks.get(endpoint_id, 0) + 1
    if _endpoint_clean_streaks[endpoint_id] >= RECOVERY_STREAK:
        await _resolve_endpoint_incident(endpoint_id)


async def evaluate_endpoint(endpoint_id: str) -> list[dict]:
    """Evaluate endpoint telemetry against alert rules."""
    raw = await redis_client.client.get(f"metrics:latest:endpoint:{endpoint_id}")
    if raw is None:
        return []

    m = json.loads(raw)
    _endpoint_heartbeats[endpoint_id] = _utcnow()

    # Do not alert while status is gray — no data yet
    if m.get("status") == "gray":
        return []

    evidence_id = m.get("packet_evidence_id")

    if not (_rules_loaded and _active_rules):
        return []

    return await _evaluate_rules(endpoint_id, m, evidence_id)


async def _evaluate_rules(endpoint_id: str, m: dict, evidence_id: str | None) -> list[dict]:
    """Evaluate all active rules against endpoint telemetry with state-based semantics.

    State-based alerting:
      - Condition becomes true + not already active → fire alert, mark active
      - Condition stays true + already active → no-op (condition persists)
      - Condition becomes false + was active → resolve alert for this rule
      - Incident closes only when ALL rules for the endpoint are resolved.
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
        state_key = (endpoint_id, rid)
        value = metric_values.get(rule["metric"])
        if value is None:
            continue

        condition_true = _evaluate_condition(value, rule["operator"], rule["threshold"])

        if condition_true:
            if state_key in _active_rule_state:
                continue
            message = (
                f"[{rule['severity'].upper()}] {rule['name']}: "
                f"{rule['metric']} {rule['operator']} {rule['threshold']} "
                f"(observed: {value:.1f}) [evidence {evidence_id}]"
            )
            aid, _ = await _fire_endpoint_alert(endpoint_id, alert_type, message, evidence_id)
            if aid:
                _active_rule_state[state_key] = aid
                fired.append({"alert_id": aid, "alert_type": alert_type, "rule_id": rid})
        else:
            if state_key in _active_rule_state:
                alert_id = _active_rule_state.pop(state_key)
                newly_resolved.append(alert_id)
                await _resolve_alert_row(alert_id)

    active_for_endpoint = any(
        state_key[0] == endpoint_id for state_key in _active_rule_state
    )

    if fired:
        _endpoint_clean_streaks[endpoint_id] = 0
    elif not active_for_endpoint:
        await _handle_endpoint_recovery(endpoint_id)

    return fired


async def _resolve_alert_row(alert_id: str) -> None:
    """Set resolved_at on a single alert row."""
    now = _utcnow()
    async with engine.begin() as conn:
        await conn.execute(
            text("UPDATE alerts SET resolved_at = :now WHERE id = :id AND resolved_at IS NULL"),
            {"now": now, "id": alert_id},
        )


async def check_endpoint_heartbeats() -> None:
    now = _utcnow()
    async with engine.begin() as conn:
        result = await conn.execute(text("SELECT id FROM endpoints"))
        endpoint_ids = [row[0] for row in result.fetchall()]

    for endpoint_id in endpoint_ids:
        last = _endpoint_heartbeats.get(endpoint_id)
        if last is None:
            continue
        if (now - last).total_seconds() > HEARTBEAT_TIMEOUT_S:
            await _fire_endpoint_alert(
                endpoint_id,
                "endpoint_heartbeat_timeout",
                f"No heartbeat for {HEARTBEAT_TIMEOUT_S}s",
            )


# ── notification delivery ────────────────────────────────────────


def _alert_severity(alert_type: str) -> str:
    """Map alert_type to notification severity."""
    critical = {
        "cpu_high", "heartbeat_timeout",
        "endpoint_packet_loss_high", "endpoint_availability_low", "endpoint_heartbeat_timeout",
    }
    return "critical" if alert_type in critical else "warning"


async def _deliver_notifications_for_node(
    node_id: str, alert_id: str, incident_id: str | None, alert_type: str, message: str,
    project_id: str | None = None,
) -> None:
    """Deliver in-app notifications for a V1 node alert."""
    from services.notifications import match_and_deliver

    if not project_id:
        return
    try:
        severity = _alert_severity(alert_type)
        async with engine.begin() as conn:
            delivered = await match_and_deliver(
                conn,
                alert_id=alert_id,
                incident_id=incident_id,
                project_id=project_id,
                alert_type=alert_type,
                message=message,
                severity=severity,
                resource_type="node",
            )
        if delivered > 0:
            logger.info("notifications: delivered %d for alert %s", delivered, alert_id)
    except Exception:
        logger.exception("notification delivery failed for node alert %s", alert_id)


async def _deliver_notifications_for_endpoint(
    endpoint_id: str, alert_id: str, incident_id: str | None, alert_type: str, message: str,
    project_id: str | None = None,
) -> None:
    """Deliver in-app notifications for a V2 endpoint alert."""
    from services.notifications import match_and_deliver

    if not project_id:
        return
    try:
        severity = _alert_severity(alert_type)
        async with engine.begin() as conn:
            delivered = await match_and_deliver(
                conn,
                alert_id=alert_id,
                incident_id=incident_id,
                project_id=project_id,
                alert_type=alert_type,
                message=message,
                severity=severity,
                resource_type="endpoint",
            )
        if delivered > 0:
            logger.info("notifications: delivered %d for endpoint alert %s", delivered, alert_id)
    except Exception:
        logger.exception("notification delivery failed for endpoint alert %s", alert_id)

# ── notification auto-resolve on incident close ─────────────────


async def _resolve_notifications_for_incident(incident_id: str) -> None:
    """Mark all notifications for an incident as resolved."""
    try:
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    "UPDATE in_app_notifications SET status = 'resolved', resolved_at = NOW() "
                    "WHERE incident_id = :incident_id AND status != 'resolved'"
                ),
                {"incident_id": incident_id},
            )
    except Exception:
        logger.exception("notification auto-resolve failed for incident %s", incident_id)
