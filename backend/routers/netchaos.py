"""V2 network chaos REST API endpoints."""

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text

from db import engine
from services.netchaos import inject, recover, status
from services.auth import CurrentUser, audit, project_clause, require_project_editor, require_project_member

router = APIRouter(prefix="/api/chaos/network", tags=["network-chaos"])


class NetworkChaosInjectIn(BaseModel):
    endpoint_id: str = Field(min_length=1)
    chaos_type: str = Field(pattern=r"^(latency|packet_loss)$")
    value: float = Field(gt=0)


class NetworkChaosRecoverIn(BaseModel):
    endpoint_id: str | None = None


def _validate_value(chaos_type: str, value: float) -> None:
    if chaos_type == "latency" and (value < 10 or value > 500):
        raise HTTPException(status_code=400, detail="Latency value must be 10–500 ms")
    if chaos_type == "packet_loss" and (value < 1 or value > 50):
        raise HTTPException(status_code=400, detail="Packet loss value must be 1–50 %")


async def _verify_endpoint_project(endpoint_id: str, project_id: str | None) -> None:
    """Raise 404 if the endpoint does not belong to the given project."""
    if not project_id:
        return  # No project context — let it through for backward compat
    clause, params = project_clause(project_id)
    params["id"] = endpoint_id
    async with engine.connect() as conn:
        row = (await conn.execute(
            text(f"SELECT 1 FROM endpoints WHERE id = :id{clause}"),
            params,
        )).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Endpoint not found in project")


@router.post("/inject")
async def inject_chaos(
    body: NetworkChaosInjectIn,
    user: CurrentUser = Depends(require_project_editor),
    project_id: str | None = Header(default=None, alias="X-Project-ID"),
):
    _validate_value(body.chaos_type, body.value)
    await _verify_endpoint_project(body.endpoint_id, project_id)
    try:
        result = await inject(body.endpoint_id, body.chaos_type, body.value)
        async with engine.begin() as conn:
            await audit(
                conn,
                action="network_chaos.injected",
                actor_user_id=user.id,
                resource_type="network_chaos",
                resource_id=body.endpoint_id,
                details={"chaos_type": body.chaos_type, "value": body.value},
                project_id=project_id,
            )
        return {"success": True, "data": result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError:
        raise HTTPException(status_code=500, detail="Chaos injection failed — check container network capability")


@router.post("/recover")
async def recover_chaos(
    body: NetworkChaosRecoverIn = None,
    user: CurrentUser = Depends(require_project_editor),
    project_id: str | None = Header(default=None, alias="X-Project-ID"),
):
    eid = body.endpoint_id if body else None
    if eid:
        await _verify_endpoint_project(eid, project_id)
    elif not body:
        # No body + no endpoint_id = system-wide recover — require explicit opt-in
        raise HTTPException(status_code=400, detail="Specify endpoint_id to recover, or pass an empty JSON body to recover all")
    result = await recover(eid)
    async with engine.begin() as conn:
        await audit(
            conn,
            action="network_chaos.recovered",
            actor_user_id=user.id,
            resource_type="network_chaos",
            resource_id=eid,
            details={},
            project_id=project_id,
        )
    return {"success": True, "data": result}


@router.get("/status")
async def chaos_status(user: CurrentUser = Depends(require_project_member)):
    return {"success": True, "data": status()}
