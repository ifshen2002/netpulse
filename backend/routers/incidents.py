from fastapi import APIRouter, Query
from sqlalchemy import text

from db import engine
from schemas import AlertOut, IncidentOut

router = APIRouter(prefix="/api/incidents", tags=["incidents"])


@router.get("")
async def list_incidents(
    status: str | None = Query(None),
    limit: int = Query(20, ge=1, le=100),
):
    clauses = []
    params = {"limit": limit}
    if status:
        clauses.append("status = :status")
        params["status"] = status

    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    sql = (
        f"SELECT id, title, status, opened_at, closed_at "
        f"FROM incidents {where} ORDER BY opened_at DESC LIMIT :limit"
    )

    async with engine.connect() as conn:
        result = await conn.execute(text(sql), params)
        rows = result.fetchall()

    data = [
        IncidentOut(
            id=r[0],
            title=r[1],
            status=r[2],
            opened_at=r[3].isoformat() if r[3] else "",
            closed_at=r[4].isoformat() if r[4] else None,
        )
        for r in rows
    ]
    return {"success": True, "data": [d.model_dump() for d in data]}


@router.get("/{incident_id}")
async def get_incident(incident_id: str):
    async with engine.connect() as conn:
        inc = await conn.execute(
            text(
                "SELECT id, title, status, opened_at, closed_at "
                "FROM incidents WHERE id = :id"
            ),
            {"id": incident_id},
        )
        inc_row = inc.first()

    if inc_row is None:
        return {
            "success": False,
            "error": {"code": "NOT_FOUND", "message": "Incident not found"},
        }

    incident = IncidentOut(
        id=inc_row[0],
        title=inc_row[1],
        status=inc_row[2],
        opened_at=inc_row[3].isoformat() if inc_row[3] else "",
        closed_at=inc_row[4].isoformat() if inc_row[4] else None,
    )

    async with engine.connect() as conn:
        alerts = await conn.execute(
            text(
                "SELECT id, node_id, incident_id, alert_type, message, "
                "fired_at, resolved_at FROM alerts "
                "WHERE incident_id = :id ORDER BY fired_at DESC"
            ),
            {"id": incident_id},
        )
        alert_rows = alerts.fetchall()

    alert_list = [
        AlertOut(
            id=a[0],
            node_id=a[1],
            incident_id=a[2],
            alert_type=a[3],
            message=a[4],
            fired_at=a[5].isoformat() if a[5] else "",
            resolved_at=a[6].isoformat() if a[6] else None,
        )
        for a in alert_rows
    ]

    return {
        "success": True,
        "data": {
            **incident.model_dump(),
            "alerts": [a.model_dump() for a in alert_list],
        },
    }
