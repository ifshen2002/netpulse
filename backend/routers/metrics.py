from fastapi import APIRouter, Depends, Header, Query
from sqlalchemy import text

from db import engine
from services.auth import CurrentUser, project_clause, require_project_member

router = APIRouter(prefix="/api/metrics", tags=["metrics"])


@router.get("/{node_id}")
async def get_metrics(
    node_id: str,
    limit: int = Query(20, ge=1, le=200),
    user: CurrentUser = Depends(require_project_member),
    project_id: str | None = Header(default=None, alias="X-Project-ID"),
):
    clause, params = project_clause(project_id)
    params["nid"] = node_id
    params["lim"] = limit
    async with engine.connect() as conn:
        rows = await conn.execute(
            text(
                f"SELECT node_id, timestamp, cpu, memory, disk, latency_ms, packet_loss_pct, status "
                f"FROM metrics WHERE node_id = :nid{clause} ORDER BY id DESC LIMIT :lim"
            ),
            params,
        )
        metrics = [
            {
                "node_id": r.node_id,
                "timestamp": r.timestamp.isoformat(),
                "cpu": r.cpu,
                "memory": r.memory,
                "disk": r.disk,
                "latency_ms": r.latency_ms,
                "packet_loss_pct": r.packet_loss_pct,
                "status": r.status,
            }
            for r in rows
        ]
    return {"success": True, "data": metrics}
