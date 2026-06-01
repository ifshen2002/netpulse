"""V2 network chaos REST API endpoints."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from services.netchaos import inject, recover, status

router = APIRouter(prefix="/api/chaos/network", tags=["network-chaos"])


class NetworkChaosInjectIn(BaseModel):
    probe_id: str = Field(min_length=1)
    chaos_type: str = Field(pattern=r"^(latency|packet_loss)$")
    value: float = Field(gt=0)


class NetworkChaosRecoverIn(BaseModel):
    probe_id: str | None = None


def _validate_value(chaos_type: str, value: float) -> None:
    if chaos_type == "latency" and (value < 10 or value > 500):
        raise HTTPException(status_code=400, detail="Latency value must be 10–500 ms")
    if chaos_type == "packet_loss" and (value < 1 or value > 50):
        raise HTTPException(status_code=400, detail="Packet loss value must be 1–50 %")


@router.post("/inject")
async def inject_chaos(body: NetworkChaosInjectIn):
    _validate_value(body.chaos_type, body.value)
    try:
        result = await inject(body.probe_id, body.chaos_type, body.value)
        return {"success": True, "data": result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/recover")
async def recover_chaos(body: NetworkChaosRecoverIn = None):
    pid = body.probe_id if body else None
    result = await recover(pid)
    return {"success": True, "data": result}


@router.get("/status")
async def chaos_status():
    return {"success": True, "data": status()}
