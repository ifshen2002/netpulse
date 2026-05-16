from fastapi import APIRouter
from sqlalchemy import text

from db import engine
from schemas import ChaosEventOut, ChaosInjectIn, ChaosRecoverIn
from services import chaos as chaos_svc
from scheduler import sync_burst_interval
from services.alerting import fire_standalone_alert
from services.simulator import any_burst, set_burst

router = APIRouter(prefix="/api/chaos", tags=["chaos"])

ALERT_ONLY_TYPES = {"db_exhaustion", "cache_unavailable"}


@router.get("/status")
async def get_status():
    state = chaos_svc.status()
    return {
        "success": True,
        "data": {
            "active": state["active"],
            "burst": {nid: any_burst(nid) for nid in ("node-2", "node-3")},
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


@router.post("/recover")
async def recover(body: ChaosRecoverIn | None = None):
    node_id = body.node_id if body else None
    removed = await chaos_svc.recover_all(node_id)
    return {"success": True, "data": {"removed": removed}}


@router.post("/burst")
async def toggle_burst(body: ChaosInjectIn):
    if body.chaos_type != "burst":
        return {
            "success": False,
            "error": {"code": "BAD_REQUEST", "message": "Use /inject for non-burst chaos types"},
        }
    enabled = bool(body.config.get("enabled", True)) if body.config else True
    set_burst(body.node_id, enabled)
    sync_burst_interval()
    return {
        "success": True,
        "data": {"node_id": body.node_id, "burst": enabled},
    }
