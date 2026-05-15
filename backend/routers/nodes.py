from fastapi import APIRouter
from sqlalchemy import text

from db import engine

router = APIRouter(prefix="/api/nodes", tags=["nodes"])


@router.get("")
async def list_nodes():
    async with engine.connect() as conn:
        rows = await conn.execute(
            text("SELECT id, name, type, status, last_seen, created_at FROM nodes ORDER BY id")
        )
        nodes = [
            {
                "id": r.id,
                "name": r.name,
                "type": r.type,
                "status": r.status,
                "last_seen": r.last_seen.isoformat() if r.last_seen else None,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ]
    return {"success": True, "data": nodes}
