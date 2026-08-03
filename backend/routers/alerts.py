from fastapi import APIRouter, Depends, Header, Query
from sqlalchemy import text

from db import engine
from schemas import AlertOut
from services.auth import CurrentUser, project_clause, require_project_member

router = APIRouter(prefix="/api/alerts", tags=["alerts"])


@router.get("")
async def list_alerts(
    node_id: str | None = Query(None),
    limit: int = Query(20, ge=1, le=100),
    user: CurrentUser = Depends(require_project_member),
    project_id: str | None = Header(default=None, alias="X-Project-ID"),
):
    clause, params = project_clause(project_id)
    params["limit"] = limit
    if node_id:
        params["node_id"] = node_id

    where = f"WHERE 1=1{clause}"
    if node_id:
        where += " AND node_id = :node_id"
    sql = (
        f"SELECT id, node_id, incident_id, alert_type, message, fired_at, resolved_at "
        f"FROM alerts {where} ORDER BY fired_at DESC LIMIT :limit"
    )

    async with engine.connect() as conn:
        result = await conn.execute(text(sql), params)
        rows = result.fetchall()

    data = [
        AlertOut(
            id=r[0],
            node_id=r[1],
            incident_id=r[2],
            alert_type=r[3],
            message=r[4],
            fired_at=r[5].isoformat() if r[5] else "",
            resolved_at=r[6].isoformat() if r[6] else None,
        )
        for r in rows
    ]
    return {"success": True, "data": [d.model_dump() for d in data]}


@router.get("/{alert_id}")
async def get_alert(
    alert_id: str,
    user: CurrentUser = Depends(require_project_member),
    project_id: str | None = Header(default=None, alias="X-Project-ID"),
):
    clause, params = project_clause(project_id)
    params["id"] = alert_id
    async with engine.connect() as conn:
        result = await conn.execute(
            text(
                f"SELECT id, node_id, incident_id, alert_type, message, "
                f"fired_at, resolved_at FROM alerts WHERE id = :id{clause}"
            ),
            params,
        )
        row = result.first()

    if row is None:
        return {"success": False, "error": {"code": "NOT_FOUND", "message": "Alert not found"}}

    d = AlertOut(
        id=row[0],
        node_id=row[1],
        incident_id=row[2],
        alert_type=row[3],
        message=row[4],
        fired_at=row[5].isoformat() if row[5] else "",
        resolved_at=row[6].isoformat() if row[6] else None,
    )
    return {"success": True, "data": d.model_dump()}
