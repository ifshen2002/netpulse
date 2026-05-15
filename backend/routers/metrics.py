from fastapi import APIRouter, Query
from sqlalchemy import text

from db import engine

router = APIRouter(prefix="/api/metrics", tags=["metrics"])


@router.get("/{node_id}")
async def get_metrics(node_id: str, limit: int = Query(20, ge=1, le=200)):
    async with engine.connect() as conn:
        rows = await conn.execute(
            text(
                "SELECT node_id, timestamp, cpu, memory, disk, latency_ms, packet_loss_pct, status "
                "FROM metrics WHERE node_id = :nid ORDER BY id DESC LIMIT :lim"
            ),
            {"nid": node_id, "lim": limit},
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
