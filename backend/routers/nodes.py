from fastapi import APIRouter, Depends, Header
from sqlalchemy import text

from db import engine
from services.auth import CurrentUser, project_clause, require_project_member

router = APIRouter(prefix="/api/nodes", tags=["nodes"])


@router.get("")
async def list_nodes(user: CurrentUser = Depends(require_project_member), project_id: str | None = Header(default=None, alias="X-Project-ID")):
    clause, params = project_clause(project_id)
    async with engine.connect() as conn:
        rows = await conn.execute(
            text(f"SELECT id, name, type, status, last_seen, created_at FROM nodes WHERE 1=1{clause} ORDER BY id"),
            params,
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
