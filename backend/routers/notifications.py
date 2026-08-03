"""Notification subscriptions and in-app notification REST API."""

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, field_validator
from sqlalchemy import text

from db import engine
from services.auth import CurrentUser, get_current_user, new_id

router = APIRouter(prefix="/api", tags=["notifications"])

VALID_RESOURCE_TYPES = {"endpoint", "node"}
VALID_SEVERITIES = {"warning", "critical"}


class SubscriptionCreateIn(BaseModel):
    project_id: str
    resource_type: str | None = None
    severity: str | None = None

    @field_validator("resource_type")
    @classmethod
    def _type_valid(cls, v: str | None) -> str | None:
        if v is not None and v not in VALID_RESOURCE_TYPES:
            raise ValueError(f"resource_type must be one of: {', '.join(sorted(VALID_RESOURCE_TYPES))}")
        return v

    @field_validator("severity")
    @classmethod
    def _severity_valid(cls, v: str | None) -> str | None:
        if v is not None and v not in VALID_SEVERITIES:
            raise ValueError(f"severity must be one of: {', '.join(sorted(VALID_SEVERITIES))}")
        return v


# ── subscriptions ──────────────────────────────────────────────


@router.get("/subscriptions")
async def list_subscriptions(user: CurrentUser = Depends(get_current_user)):
    async with engine.connect() as conn:
        rows = (await conn.execute(
            text(
                "SELECT ns.id, ns.project_id, p.name AS project_name, "
                "ns.resource_type, ns.severity, ns.enabled, ns.created_at "
                "FROM notification_subscriptions ns "
                "JOIN projects p ON p.id = ns.project_id "
                "WHERE ns.user_id = :user_id "
                "ORDER BY ns.created_at DESC"
            ),
            {"user_id": user.id},
        )).fetchall()

    return {
        "success": True,
        "data": [
            {
                "id": r[0],
                "project_id": r[1],
                "project_name": r[2],
                "resource_type": r[3],
                "severity": r[4],
                "enabled": r[5],
                "created_at": r[6].isoformat() if r[6] else None,
            }
            for r in rows
        ],
    }


@router.post("/subscriptions", status_code=201)
async def create_subscription(body: SubscriptionCreateIn, user: CurrentUser = Depends(get_current_user)):
    sub_id = new_id()
    async with engine.begin() as conn:
        # Verify project exists
        project = (await conn.execute(
            text("SELECT 1 FROM projects WHERE id = :id"), {"id": body.project_id}
        )).fetchone()
        if project is None:
            raise HTTPException(status_code=404, detail="Project not found")

        # Check for duplicate
        existing = (await conn.execute(
            text(
                "SELECT 1 FROM notification_subscriptions "
                "WHERE user_id = :user_id AND project_id = :project_id "
                "AND resource_type IS NOT DISTINCT FROM :resource_type "
                "AND severity IS NOT DISTINCT FROM :severity"
            ),
            {
                "user_id": user.id,
                "project_id": body.project_id,
                "resource_type": body.resource_type,
                "severity": body.severity,
            },
        )).fetchone()
        if existing:
            raise HTTPException(status_code=409, detail="Subscription already exists")

        await conn.execute(
            text(
                "INSERT INTO notification_subscriptions "
                "(id, user_id, project_id, resource_type, severity, enabled, created_at) "
                "VALUES (:id, :user_id, :project_id, :resource_type, :severity, true, NOW())"
            ),
            {
                "id": sub_id,
                "user_id": user.id,
                "project_id": body.project_id,
                "resource_type": body.resource_type,
                "severity": body.severity,
            },
        )

    return {
        "success": True,
        "data": {
            "id": sub_id,
            "project_id": body.project_id,
            "resource_type": body.resource_type,
            "severity": body.severity,
        },
    }


@router.delete("/subscriptions/{subscription_id}")
async def delete_subscription(subscription_id: str, user: CurrentUser = Depends(get_current_user)):
    async with engine.begin() as conn:
        result = await conn.execute(
            text(
                "DELETE FROM notification_subscriptions "
                "WHERE id = :id AND user_id = :user_id"
            ),
            {"id": subscription_id, "user_id": user.id},
        )
        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail="Subscription not found")

    return {"success": True, "data": {"deleted": subscription_id}}


# ── notifications ──────────────────────────────────────────────


@router.get("/notifications")
async def list_notifications(
    status: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    user: CurrentUser = Depends(get_current_user),
):
    clauses = ["user_id = :user_id"]
    params = {"user_id": user.id, "limit": limit}
    if status:
        clauses.append("status = :status")
        params["status"] = status

    where = "WHERE " + " AND ".join(clauses)
    async with engine.connect() as conn:
        rows = (await conn.execute(
            text(
                f"SELECT id, alert_id, incident_id, project_id, title, body, "  # nosec B608
                "severity, status, created_at, read_at, acknowledged_at, resolved_at "
                "FROM in_app_notifications "
                f"{where} ORDER BY created_at DESC LIMIT :limit"
            ),
            params,
        )).fetchall()

    return {
        "success": True,
        "data": [
            {
                "id": r[0],
                "alert_id": r[1],
                "incident_id": r[2],
                "project_id": r[3],
                "title": r[4],
                "body": r[5],
                "severity": r[6],
                "status": r[7],
                "created_at": r[8].isoformat() if r[8] else None,
                "read_at": r[9].isoformat() if r[9] else None,
                "acknowledged_at": r[10].isoformat() if r[10] else None,
                "resolved_at": r[11].isoformat() if r[11] else None,
            }
            for r in rows
        ],
    }


@router.get("/notifications/unread-count")
async def unread_count(user: CurrentUser = Depends(get_current_user)):
    async with engine.connect() as conn:
        count = (await conn.execute(
            text(
                "SELECT COUNT(*) FROM in_app_notifications "
                "WHERE user_id = :user_id AND status = 'unread'"
            ),
            {"user_id": user.id},
        )).scalar_one()

    return {"success": True, "data": {"count": count}}


@router.patch("/notifications/{notification_id}/read")
async def mark_read(notification_id: str, user: CurrentUser = Depends(get_current_user)):
    async with engine.begin() as conn:
        result = await conn.execute(
            text(
                "UPDATE in_app_notifications SET status = 'read', read_at = NOW() "
                "WHERE id = :id AND user_id = :user_id AND status = 'unread'"
            ),
            {"id": notification_id, "user_id": user.id},
        )
        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail="Notification not found or already read")

    return {"success": True, "data": {"id": notification_id, "status": "read"}}


@router.patch("/notifications/{notification_id}/acknowledge")
async def acknowledge(notification_id: str, user: CurrentUser = Depends(get_current_user)):
    async with engine.begin() as conn:
        result = await conn.execute(
            text(
                "UPDATE in_app_notifications SET status = 'acknowledged', acknowledged_at = NOW() "
                "WHERE id = :id AND user_id = :user_id AND status IN ('unread', 'read')"
            ),
            {"id": notification_id, "user_id": user.id},
        )
        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail="Notification not found or already acknowledged")

    return {"success": True, "data": {"id": notification_id, "status": "acknowledged"}}
