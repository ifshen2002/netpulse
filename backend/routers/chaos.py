import json

from fastapi import APIRouter
from redis_client import client as redis
from schemas import ChaosInjectIn, ChaosRecoverIn
from services import chaos as chaos_svc
from services.chaos import OVERLAY_TYPES
from scheduler import sync_burst_interval
from services.alerting import clear_cooldown, fire_standalone_alert
from services.simulator import set_burst

router = APIRouter(prefix="/api/chaos", tags=["chaos"])

ALERT_ONLY_TYPES = {"db_exhaustion", "cache_unavailable"}

# chaos_type → alert_type for cooldown clearance
_CHAOS_ALERT_MAP = {"cpu_spike": "cpu_high", "latency_spike": "latency_spike"}


@router.get("/status")
async def get_status():
    state = chaos_svc.status()
    from services.simulator import get_burst_interval
    return {
        "success": True,
        "data": {
            "active": state["active"],
            "burst": {nid: get_burst_interval(nid) for nid in ("node-2", "node-3")},
        },
    }


@router.post("/inject")
async def inject(body: ChaosInjectIn):
    try:
        event_id = await chaos_svc.inject(
            body.node_id, body.chaos_type, body.config
        )
    except ValueError as exc:
        return {
            "success": False,
            "error": {"code": "BAD_REQUEST", "message": str(exc)},
        }

    if body.chaos_type in ALERT_ONLY_TYPES:
        await fire_standalone_alert(
            body.node_id,
            body.chaos_type,
            f"Chaos injected: {body.chaos_type} on {body.node_id}",
        )
        return {"success": True, "data": {"event_id": event_id}}

    # For overlay types: clear cooldown + force immediate evaluation so the
    # operator sees alert/incident within seconds, not "whenever the next
    # scheduler cycle happens to align."
    if body.chaos_type in OVERLAY_TYPES:
        alert_type = _CHAOS_ALERT_MAP.get(body.chaos_type)
        if alert_type:
            clear_cooldown(body.node_id, alert_type)

        if body.node_id in ("node-2", "node-3"):
            from services.alerting import evaluate as evaluate_node
            from services.simulator import generate as generate_synthetic
            from services.normalization import normalize
            from routers.websocket import manager

            raw = generate_synthetic(body.node_id)
            if raw:
                m = normalize(raw)
                m = chaos_svc.apply_overlay(m)
                if m:
                    await redis.set(
                        f"metrics:latest:{m['node_id']}",
                        json.dumps(m),
                    )
                    # Broadcast metric immediately so frontend
                    # updates without waiting for push_metrics cycle.
                    await manager.broadcast(
                        json.dumps(
                            {
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
                        )
                    )
                    await evaluate_node(body.node_id)

    return {"success": True, "data": {"event_id": event_id}}


@router.post("/recover")
async def recover(body: ChaosRecoverIn | None = None):
    node_id = body.node_id if body else None
    chaos_type = body.chaos_type if body else None
    removed = await chaos_svc.recover_all(node_id, chaos_type)
    if removed > 0:
        from services.alerting import resolve_for_node as _resolve
        if node_id:
            await _resolve(node_id)
        else:
            for nid in ("node-2", "node-3"):
                await _resolve(nid)
    return {"success": True, "data": {"removed": removed}}


@router.post("/burst")
async def set_burst_endpoint(body: ChaosInjectIn):
    if body.chaos_type != "burst":
        return {
            "success": False,
            "error": {"code": "BAD_REQUEST", "message": "Use /inject for non-burst chaos types"},
        }
    interval = int(body.config.get("interval", 1)) if body.config else 1
    if interval not in (0, 1, 5, 15, 60):
        return {
            "success": False,
            "error": {
                "code": "BAD_REQUEST",
                "message": "Interval must be 0 (off), 1, 5, 15, or 60",
            },
        }
    set_burst(body.node_id, interval)
    sync_burst_interval()
    return {
        "success": True,
        "data": {"node_id": body.node_id, "burst": interval > 0, "interval": interval},
    }
